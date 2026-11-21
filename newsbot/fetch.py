"""Fetch RSS/Atom feeds and normalize entries into Articles."""
from __future__ import annotations

import calendar
import hashlib
import html
import logging
import re
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from typing import Callable
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import feedparser
import requests

from .config import Settings, Source

log = logging.getLogger(__name__)

TRACKING_PARAMS = {"fbclid", "gclid", "ocid", "cmpid", "ref"}
FUTURE_TOLERANCE = timedelta(hours=1)
SUMMARY_CHARS = 300


@dataclass
class Article:
    id: str
    title: str
    url: str
    source: str
    category: str
    published_at: datetime  # tz-aware UTC
    summary: str

    def to_dict(self) -> dict:
        d = asdict(self)
        d["published_at"] = iso(self.published_at)
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "Article":
        return cls(**{**d, "published_at": parse_iso(d["published_at"])})


def iso(dt: datetime) -> str:
    return dt.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_iso(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(UTC)


def canonicalize_url(url: str) -> str:
    parts = urlsplit(url.strip())
    query = [
        (k, v)
        for k, v in parse_qsl(parts.query, keep_blank_values=True)
        if not k.lower().startswith("utm_") and k.lower() not in TRACKING_PARAMS
    ]
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path, urlencode(query), ""))


def article_id(url: str) -> str:
    return hashlib.sha1(canonicalize_url(url).encode()).hexdigest()[:16]


def _clean_text(raw: str) -> str:
    text = html.unescape(re.sub(r"<[^>]+>", " ", raw or ""))
    return re.sub(r"\s+", " ", text).strip()


def _entry_date(entry) -> datetime | None:
    parsed = entry.get("published_parsed") or entry.get("updated_parsed")
    if not parsed:
        return None
    # feedparser normalizes to UTC; naive inputs are treated as UTC.
    return datetime.fromtimestamp(calendar.timegm(parsed), tz=UTC)


def parse_feed(content: bytes, source: Source, now: datetime, window_hours: int) -> list[Article]:
    feed = feedparser.parse(content)
    cutoff = now - timedelta(hours=window_hours)
    out = []
    for entry in feed.entries:
        link = entry.get("link")
        title = _clean_text(entry.get("title", ""))
        published = _entry_date(entry)
        if not link or not title or published is None:
            continue
        if published > now + FUTURE_TOLERANCE:
            published = now
        if published < cutoff:
            continue
        suffix = source.strip_title_suffix
        if suffix and title.endswith(suffix):
            title = title[: -len(suffix)].rstrip()
        summary = _clean_text(entry.get("summary", ""))
        if len(summary) > SUMMARY_CHARS:
            summary = summary[: SUMMARY_CHARS - 1].rstrip() + "…"
        url = canonicalize_url(link)
        out.append(Article(article_id(url), title, url, source.name, source.category, published, summary))
    return out


def default_get(url: str, timeout: int) -> bytes:
    resp = requests.get(url, timeout=timeout, headers={"User-Agent": "newsbot/1.0"})
    resp.raise_for_status()
    return resp.content


def fetch_all(
    sources: list[Source],
    now: datetime,
    settings: Settings,
    http_get: Callable[[str, int], bytes] = default_get,
) -> tuple[list[Article], list[str]]:
    seen: dict[str, Article] = {}
    errors: list[str] = []
    for source in sources:
        try:
            articles = parse_feed(http_get(source.url, settings.fetch_timeout_s), source, now, settings.window_hours)
        except Exception as e:  # one dead feed must never stop the run
            msg = f"{source.name}: {type(e).__name__}: {e}"
            log.warning("feed failed: %s", msg)
            errors.append(msg)
            continue
        for a in articles:
            seen.setdefault(a.id, a)
    return sorted(seen.values(), key=lambda a: a.published_at, reverse=True), errors
