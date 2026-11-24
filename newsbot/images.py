"""Find candidate images for each pick: search free sources, rank with a local Ollama vision model."""
from __future__ import annotations

import json
from urllib.parse import quote, quote_plus

import requests

from .config import IMAGE_SOURCES
from .fetch import _clean_text, _http_url

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


def search_steam(query: str, http_get, timeout: int) -> list[dict]:
    found = _get_json(f"https://store.steampowered.com/api/storesearch/?term={quote(query)}&l=english&cc=US",
                      http_get, timeout)
    items = found.get("items") or []
    if not items:
        return []
    app_id = items[0].get("id")
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
