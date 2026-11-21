"""Ask Claude to pick stories for one category and draft posts."""
from __future__ import annotations

import json
import subprocess
from collections import defaultdict
from datetime import datetime
from typing import Callable

import anthropic
from pydantic import BaseModel, ValidationError

from .config import Category, Settings
from .fetch import Article, iso

MAX_TOKENS = 4000
FALLBACK_BETA = "server-side-fallback-2026-07-01"
CLI_TIMEOUT_S = 300

# (system_prompt, user_message) -> (picks, usage)
Curator = Callable[[str, str], tuple[list[dict], dict]]


class Pick(BaseModel):
    article_id: str
    post: str
    reason: str
    card_text: str


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
    return _api_parse(client, settings, system_prompt, user_message)[0]


def _api_parse(client, settings: Settings, system_prompt: str, user_message: str):
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
    except Exception as e:
        # The SDK parses the JSON inside parse(), so a refusal or a cut-off reply surfaces
        # here as a validation error; a missing API key surfaces as TypeError. Either way
        # this category fails and the run carries on.
        raise CurationError(f"{type(e).__name__}: {str(e)[:200]}") from e
    if response.stop_reason in ("refusal", "max_tokens"):
        raise CurationError(f"stop_reason={response.stop_reason}")
    parsed = response.parsed_output
    if not isinstance(parsed, CurationResult):
        raise CurationError("no parsed output")
    return [p.model_dump() for p in parsed.picks], response


USAGE_KEYS = ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens", "output_tokens", "thinking_tokens")


def empty_usage(model: str) -> dict:
    return {"model": model, **{k: 0 for k in USAGE_KEYS}, "cost_usd_equiv": 0.0}


def api_curator(client, settings: Settings) -> Curator:
    def curate(system_prompt: str, user_message: str) -> tuple[list[dict], dict]:
        picks, response = _api_parse(client, settings, system_prompt, user_message)
        usage = empty_usage(settings.model)
        u = getattr(response, "usage", None)
        for k in USAGE_KEYS[:-1]:
            usage[k] = int(getattr(u, k, 0) or 0)
        return picks, usage

    return curate


def claude_code_curator(settings: Settings, runner=subprocess.run, claude_bin: str = "claude") -> Curator:
    """Curate through the Claude Code CLI, which uses the owner's Claude Pro/Max login."""
    schema = json.dumps(CurationResult.model_json_schema())

    def curate(system_prompt: str, user_message: str) -> tuple[list[dict], dict]:
        argv = [
            claude_bin, "-p",
            "--model", settings.model,
            "--system-prompt", system_prompt,
            "--json-schema", schema,
            "--tools", "",
            "--strict-mcp-config",
            "--setting-sources", "",
            "--no-session-persistence",
            "--output-format", "json",
        ]
        try:
            proc = runner(argv, input=user_message, capture_output=True, text=True, timeout=CLI_TIMEOUT_S)
        except FileNotFoundError as e:
            raise CurationError("claude CLI not found on PATH") from e
        except subprocess.TimeoutExpired as e:
            raise CurationError(f"claude CLI timed out after {CLI_TIMEOUT_S}s") from e
        try:
            out = json.loads(proc.stdout or "")
        except json.JSONDecodeError:
            out = None
        if not isinstance(out, dict):
            detail = (proc.stderr or proc.stdout or "").strip()[:200]
            raise CurationError(f"claude CLI exit {proc.returncode}: {detail}")
        if out.get("is_error") or proc.returncode != 0:
            raise CurationError(f"claude CLI error: {str(out.get('result') or out.get('subtype'))[:200]}")
        try:
            parsed = CurationResult.model_validate(out.get("structured_output"))
        except ValidationError as e:
            raise CurationError(f"no valid structured output: {str(out.get('result'))[:120]}") from e
        return [p.model_dump() for p in parsed.picks], _cli_usage(out, settings.model)

    return curate


def _cli_usage(out: dict, fallback_model: str) -> dict:
    u = out.get("usage") or {}
    models = list((out.get("modelUsage") or {}).keys())
    usage = empty_usage(models[0] if models else fallback_model)
    for k in USAGE_KEYS[:-1]:
        usage[k] = int(u.get(k) or 0)
    usage["thinking_tokens"] = int((u.get("output_tokens_details") or {}).get("thinking_tokens") or 0)
    usage["cost_usd_equiv"] = float(out.get("total_cost_usd") or 0.0)
    return usage


def make_curator(settings: Settings, model_override: str | None = None) -> Curator:
    if model_override:
        settings = Settings(**{**settings.__dict__, "model": model_override})
    if settings.backend == "api":
        return api_curator(anthropic.Anthropic(), settings)
    return claude_code_curator(settings, runner=lambda *a, **k: subprocess.run(*a, **k))
