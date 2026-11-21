"""Ask Claude to pick stories for one category and draft posts."""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime

import anthropic
from pydantic import BaseModel

from .config import Category, Settings
from .fetch import Article, iso

MAX_TOKENS = 4000
FALLBACK_BETA = "server-side-fallback-2026-07-01"


class Pick(BaseModel):
    article_id: str
    post: str
    reason: str


class CurationResult(BaseModel):
    picks: list[Pick]


class CurationError(Exception):
    pass


def select_candidates(articles: list[Article], category_id: str, per_source_cap: int) -> list[Article]:
    per_source: dict[str, list[Article]] = defaultdict(list)
    for a in sorted(articles, key=lambda a: a.published_at, reverse=True):
        if a.category == category_id and len(per_source[a.source]) < per_source_cap:
            per_source[a.source].append(a)
    flat = [a for group in per_source.values() for a in group]
    return sorted(flat, key=lambda a: a.published_at, reverse=True)


def build_system_prompt(template: str, category: Category) -> str:
    return (
        template.replace("{category_name}", category.name)
        .replace("{covers}", category.covers)
        .replace("{skip}", category.skip)
        .replace("{max_picks}", str(category.max_picks))
    )


def build_user_message(candidates: list[Article], previous_picks: list[dict], now: datetime) -> str:
    lines = [f"Current time (UTC): {iso(now)}", "", "Already covered (last 24h):"]
    if previous_picks:
        lines += [f"- [{p.get('category', '?')}] {p.get('title', '')} — {p.get('post', '')}" for p in previous_picks]
    else:
        lines.append("none")
    lines += ["", "Candidates:"]
    for a in candidates:
        hours = max(0, int((now - a.published_at).total_seconds() // 3600))
        lines += [
            "",
            f"id: {a.id}",
            f"source: {a.source} | published: {iso(a.published_at)} ({hours}h ago)",
            f"title: {a.title}",
            f"summary: {a.summary}",
        ]
    return "\n".join(lines)


def curate_category(client, settings: Settings, system_prompt: str, user_message: str) -> list[dict]:
    try:
        response = client.beta.messages.parse(
            model=settings.model,
            max_tokens=MAX_TOKENS,
            system=system_prompt,
            messages=[{"role": "user", "content": user_message}],
            output_format=CurationResult,
            output_config={"effort": settings.effort},
            betas=[FALLBACK_BETA],
            fallbacks="default",
        )
    except anthropic.APIError as e:
        raise CurationError(f"API error: {type(e).__name__}: {e}") from e
    if response.stop_reason in ("refusal", "max_tokens"):
        raise CurationError(f"stop_reason={response.stop_reason}")
    parsed = response.parsed_output
    if not isinstance(parsed, CurationResult):
        raise CurationError("no parsed output")
    return [p.model_dump() for p in parsed.picks]
