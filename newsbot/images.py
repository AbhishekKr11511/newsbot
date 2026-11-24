"""Find candidate images for each pick: search free sources, rank with a local Ollama vision model."""
from __future__ import annotations

import base64
import ipaddress
import json
import logging
import re
import socket
import time
from typing import Callable
from urllib.parse import quote, quote_plus, urljoin, urlsplit

import requests

from .config import IMAGE_SOURCES, ImageSettings
from .fetch import USER_AGENT, _clean_text, _http_url, default_get, read_capped

log = logging.getLogger(__name__)

MAX_SEARCHES = 3
MAX_QUERY_CHARS = 80


def clean_searches(raw) -> list[dict]:
    """Keep up to 3 valid {source, query} entries from Claude's output; drop the rest silently."""
    out = []
    for item in raw or []:
        if not isinstance(item, dict):
            continue
        source = str(item.get("source") or "").strip().lower()
        query = str(item.get("query") or "").strip()
        if source in IMAGE_SOURCES and query and len(query) <= MAX_QUERY_CHARS:
            out.append({"source": source, "query": query})
    return out[:MAX_SEARCHES]


def screenshot_link(raw) -> dict | None:
    """Turn Claude's {text, search} into {text, url}. The URL is always a search link we build."""
    if not isinstance(raw, dict):
        return None
    text = str(raw.get("text") or "").strip()
    search = str(raw.get("search") or "").strip()
    if not text or not search:
        return None
    return {"text": text, "url": "https://www.google.com/search?q=" + quote_plus(search)}


# ---- sources ---------------------------------------------------------------
# Each source: (query, http_get, timeout) -> list of candidates
#   {url, thumb, page_url, source, credit, license}
# JSON APIs only. HTTP 429 raises SourceUnavailable (the caller stops using that source for the run).

PER_QUERY = 5
STEAM_SCREENSHOTS = 2


class SourceUnavailable(Exception):
    pass


def _get_json(url: str, http_get, timeout: int):
    try:
        return json.loads(http_get(url, timeout))
    except requests.HTTPError as e:
        if getattr(e.response, "status_code", None) == 429:
            raise SourceUnavailable(url) from e
        raise


def _candidate(source, url, thumb, page_url, credit, license) -> dict | None:
    url = _http_url(url)
    thumb = _http_url(thumb) or url
    if not url:
        return None
    return {"url": url, "thumb": thumb, "page_url": _http_url(page_url) or url, "source": source,
            "credit": credit, "license": license}


def search_wikimedia(query: str, http_get, timeout: int) -> list[dict]:
    q = quote(f"{query} filetype:bitmap")
    url = ("https://commons.wikimedia.org/w/api.php?action=query&format=json&generator=search"
           f"&gsrsearch={q}&gsrnamespace=6&gsrlimit={PER_QUERY}&prop=imageinfo"
           "&iiprop=url%7Cextmetadata%7Cmime&iiurlwidth=640")
    data = _get_json(url, http_get, timeout)
    pages = sorted((data.get("query") or {}).get("pages", {}).values(), key=lambda p: p.get("index", 0))
    out = []
    for page in pages:
        info = (page.get("imageinfo") or [{}])[0]
        meta = info.get("extmetadata") or {}
        credit = _clean_text((meta.get("Artist") or {}).get("value", "")) or "Wikimedia Commons"
        license = _clean_text((meta.get("LicenseShortName") or {}).get("value", "")) or "See source"
        c = _candidate("wikimedia", info.get("url"), info.get("thumburl"), info.get("descriptionurl"), credit, license)
        if c:
            out.append(c)
    return out[:PER_QUERY]


def _words(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


def search_steam(query: str, http_get, timeout: int) -> list[dict]:
    found = _get_json(f"https://store.steampowered.com/api/storesearch/?term={quote(query)}&l=english&cc=US",
                      http_get, timeout)
    # Steam returns its nearest match even for games it doesn't sell ("GTA VI" -> GTA V), and the vision
    # model can't tell those apart, so the store name must contain every word of the query.
    wanted = set(_words(query))
    match = next((i for i in found.get("items") or [] if wanted <= set(_words(i.get("name", "")))), None)
    if not match:
        return []
    app_id = match.get("id")
    details = _get_json(f"https://store.steampowered.com/api/appdetails?appids={app_id}", http_get, timeout)
    entry = details.get(str(app_id)) or {}
    if not entry.get("success"):
        return []
    data = entry.get("data") or {}
    page = f"https://store.steampowered.com/app/{app_id}/"
    raw = [(data.get("header_image"), data.get("header_image"))]
    raw += [(s.get("path_full"), s.get("path_thumbnail")) for s in (data.get("screenshots") or [])[:STEAM_SCREENSHOTS]]
    out = [_candidate("steam", u, t, page, "Official art · Steam", "Promotional") for u, t in raw]
    return [c for c in out if c]


def _openverse_license(code: str, version: str) -> str:
    code = (code or "").lower()
    if code == "cc0":
        return "CC0"
    if code == "pdm":
        return "Public domain"
    return f"CC {code.upper()} {version}".strip()


def search_openverse(query: str, http_get, timeout: int) -> list[dict]:
    url = (f"https://api.openverse.org/v1/images/?q={quote(query)}&page_size={PER_QUERY}"
           "&license_type=commercial,modification")
    data = _get_json(url, http_get, timeout)
    out = []
    for r in data.get("results") or []:
        credit = f"{r.get('title') or 'Untitled'} by {r.get('creator') or 'unknown'} ({r.get('source') or 'openverse'})"
        # thumb = the direct image: Openverse's own /thumb/ endpoint counts against its anonymous rate limit.
        c = _candidate("openverse", r.get("url"), r.get("url"), r.get("foreign_landing_url"), credit,
                       _openverse_license(r.get("license"), r.get("license_version") or ""))
        if c:
            out.append(c)
    return out[:PER_QUERY]


SOURCES = {"wikimedia": search_wikimedia, "steam": search_steam, "openverse": search_openverse}


# ---- thumbnail download ---------------------------------------------------------
# Candidate image URLs come from third-party indexes (Openverse points at arbitrary hosts), so the
# download used for ranking refuses anything that resolves to a non-public address (router, localhost,
# cloud metadata) and checks every redirect hop the same way.

MAX_REDIRECTS = 3


def _is_public_host(host: str | None) -> bool:
    if not host:
        return False
    try:
        infos = socket.getaddrinfo(host, None)
    except OSError:
        return False
    for info in infos:
        ip = ipaddress.ip_address(info[4][0].split("%", 1)[0])
        if not ip.is_global or ip.is_multicast:
            return False
    return bool(infos)


def public_get(url: str, timeout: int) -> bytes:
    started = time.monotonic()
    for _ in range(MAX_REDIRECTS + 1):
        if not _http_url(url) or not _is_public_host(urlsplit(url).hostname):
            raise ValueError(f"refusing non-public image host: {url}")
        resp = requests.get(url, timeout=timeout, headers={"User-Agent": USER_AGENT}, stream=True,
                            allow_redirects=False)
        try:
            if resp.is_redirect:
                url = urljoin(url, resp.headers["Location"])
                continue
            resp.raise_for_status()
            return read_capped(resp, started)
        finally:
            resp.close()
    raise ValueError("too many redirects")


# ---- ranking -----------------------------------------------------------------

OLLAMA_TIMEOUT_S = 60
MAX_PER_SOURCE = 2
_DROPPED = object()  # thumbnail couldn't be downloaded: never shown

# A small local model (gemma3:4b) describes images well but gives almost everything 8/10 when asked
# for a free score. A yes / partly / no check against the search term separates them reliably.
RANK_PROMPT = (
    "A news account wants a picture for this X post:\n\n{post}\n\n"
    "Describe what this image shows in at most 12 words. Then answer: does it clearly show {query}? "
    "Answer \"yes\", \"partly\" or \"no\". Also say whether it is a clear, usable picture "
    "(not mostly text, not blank, not blurry)."
)
RANK_SCHEMA = {
    "type": "object",
    "properties": {"shows": {"type": "string"}, "match": {"type": "string", "enum": ["yes", "partly", "no"]},
                   "usable": {"type": "boolean"}},
    "required": ["shows", "match", "usable"],
}
MATCH_SCORES = {"yes": 9, "partly": 6, "no": 2}
UNUSABLE_PENALTY = 3

# (image bytes, post text, search query) -> score 0..10; raises RankError on any failure
Ranker = Callable[[bytes, str, str], int]


class RankError(Exception):
    pass


def ollama_ranker(cfg: ImageSettings, post=requests.post) -> Ranker:
    def rank(image: bytes, post_text: str, query: str) -> int:
        body = {
            "model": cfg.ollama_model,
            "stream": False,
            "format": RANK_SCHEMA,
            "options": {"temperature": 0},
            "messages": [{"role": "user", "content": RANK_PROMPT.format(post=post_text, query=query),
                          "images": [base64.b64encode(image).decode()]}],
        }
        try:
            resp = post(f"{cfg.ollama_url}/api/chat", json=body, timeout=OLLAMA_TIMEOUT_S)
            resp.raise_for_status()
            answer = json.loads(resp.json()["message"]["content"])
            score = MATCH_SCORES[answer["match"]] - (0 if answer.get("usable", True) else UNUSABLE_PENALTY)
            return max(0, min(10, score))
        except Exception as e:  # connection refused, model missing, junk output: all mean "can't rank"
            raise RankError(str(e)) from e
    return rank


# ---- orchestration -------------------------------------------------------------

def _interleave(lists: list[list[dict]]) -> list[dict]:
    out, seen = [], set()
    for i in range(max((len(x) for x in lists), default=0)):
        for lst in lists:
            if i < len(lst) and lst[i]["url"] not in seen:
                seen.add(lst[i]["url"])
                out.append(lst[i])
    return out


def _gather(pick, cfg, timeout, http_get, sources, disabled, over) -> list[dict]:
    results = []
    for s in pick.get("image_searches") or []:
        src = s.get("source")
        if src not in cfg.sources or src in disabled or src not in sources:
            continue
        if over():
            break
        try:
            found = sources[src](s["query"], http_get, timeout)
            results.append([{**c, "query": s["query"]} for c in found])
        except SourceUnavailable:
            log.warning("image source %s unavailable (rate limited); skipping it this run", src)
            disabled.add(src)
        except Exception as e:  # one bad search never costs the others
            log.warning("image search %s %r failed: %s", src, s.get("query"), e)
    return _interleave(results)


def _select(pool: list[dict], scores: dict, fully_ranked: bool, cfg: ImageSettings) -> list[dict]:
    ranked = [(c, scores[c["url"]]) for c in pool
              if c["url"] in scores and scores[c["url"]] is not _DROPPED and scores[c["url"]] >= cfg.min_score]
    ranked.sort(key=lambda cs: cs[1], reverse=True)
    ordered = [{**c, "score": s} for c, s in ranked]
    if not fully_ranked:  # ranking was cut short (or never ran): fill with what wasn't judged
        ordered += [{**c, "score": None} for c in pool if c["url"] not in scores]
    out, per_source = [], {}
    for c in ordered:
        if per_source.get(c["source"], 0) < MAX_PER_SOURCE:
            per_source[c["source"]] = per_source.get(c["source"], 0) + 1
            out.append(c)
    return out[:cfg.keep]


def find_images(picks: list[dict], cfg: ImageSettings, fetch_timeout: int, http_get=default_get,
                ranker: Ranker | None = None, clock=time.monotonic, sources=None, thumb_get=public_get) -> None:
    """Set pick["images"] on every pick, in place. Never raises for a single pick's trouble."""
    sources = sources or SOURCES
    start = clock()

    def over() -> bool:
        return clock() - start >= cfg.budget_s

    # Phase 1: search (HTTP only).
    disabled: set[str] = set()
    pools: list[list[dict]] = []
    for pick in picks:
        try:
            pools.append([] if over() else _gather(pick, cfg, fetch_timeout, http_get, sources, disabled, over))
        except Exception as e:
            log.warning("image search failed for a pick: %s", e)
            pools.append([])

    # Phase 2: rank round-robin across picks, so a slow model can't starve the last category.
    queues = [pool[:cfg.max_scored] for pool in pools]
    scores: list[dict] = [{} for _ in picks]
    done = [0] * len(picks)
    alive = ranker is not None
    while alive and any(done[k] < len(queues[k]) for k in range(len(picks))):
        for k, queue in enumerate(queues):
            if done[k] >= len(queue):
                continue
            if over():
                alive = False
                break
            c = queue[done[k]]
            done[k] += 1
            try:
                image = thumb_get(c["thumb"], fetch_timeout)
            except Exception:
                scores[k][c["url"]] = _DROPPED
                continue
            try:
                scores[k][c["url"]] = ranker(image, picks[k].get("post", ""), c.get("query", ""))
            except RankError as e:
                log.warning("image ranking stopped for this run: %s", e)
                done[k] -= 1  # not judged
                alive = False
                break

    for k, pick in enumerate(picks):
        try:
            fully_ranked = ranker is not None and done[k] >= len(queues[k])
            pick["images"] = _select(pools[k], scores[k], fully_ranked, cfg)
        except Exception as e:
            log.warning("image selection failed for a pick: %s", e)
            pick["images"] = []
