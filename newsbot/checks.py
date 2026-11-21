"""Sanity checks on Claude's picks and drafted posts."""
from __future__ import annotations

import re

from .config import Settings

HASHTAG = re.compile(r"#\w")
LINK = re.compile(r"https?://|www\.", re.IGNORECASE)


def check_post(text: str, settings: Settings) -> list[str]:
    text = text.strip()
    if not text:
        return ["empty"]
    flags = []
    if len(text) > settings.max_post_chars:
        flags.append("too_long")
    if HASHTAG.search(text):
        flags.append("hashtag")
    if LINK.search(text):
        flags.append("link")
    lower = text.lower()
    flags += [f"hype:{w}" for w in settings.banned_words if w.lower() in lower]
    return flags


def validate_picks(picks: list[dict], candidate_ids: set[str], already_picked_ids: set[str], max_picks: int) -> list[dict]:
    out, seen = [], set()
    for pick in picks:
        pid = pick.get("article_id")
        if pid not in candidate_ids or pid in already_picked_ids or pid in seen:
            continue
        seen.add(pid)
        out.append(pick)
    return out[:max_picks]
