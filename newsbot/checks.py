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


CARD_MAX_CHARS = 60


def check_card(text: str) -> list[str]:
    text = (text or "").strip()
    if not text:
        return ["card_empty"]
    flags = []
    if len(text) > CARD_MAX_CHARS:
        flags.append("card_too_long")
    if HASHTAG.search(text):
        flags.append("card_hashtag")
    if LINK.search(text):
        flags.append("card_link")
    return flags


PLACEHOLDER = re.compile(r"\b(placeholder|lorem ipsum|tbd|todo)\b", re.IGNORECASE)
MIN_POST_CHARS = 8


def _looks_unfinished(post: str) -> bool:
    """Models occasionally return template text instead of a real draft."""
    post = (post or "").strip()
    return len(post) < MIN_POST_CHARS or bool(PLACEHOLDER.search(post))


def validate_picks(picks: list[dict], candidate_ids: set[str], already_picked_ids: set[str], max_picks: int) -> list[dict]:
    out, seen = [], set()
    for pick in picks:
        pid = pick.get("article_id")
        if pid not in candidate_ids or pid in already_picked_ids or pid in seen:
            continue
        if _looks_unfinished(pick.get("post", "")):
            continue
        seen.add(pid)
        out.append(pick)
    return out[:max_picks]
