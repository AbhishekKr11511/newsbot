"""Find candidate images for each pick: search free sources, rank with a local Ollama vision model."""
from __future__ import annotations

from urllib.parse import quote_plus

from .config import IMAGE_SOURCES

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
