"""One bot run: fetch → curate per category → check → store."""
from __future__ import annotations

import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import TextIO

from . import store
from .checks import check_card, check_post, validate_picks
from .config import Category, Settings, load_categories, load_settings, load_sources
from .curate import (
    USAGE_KEYS, CurationError, Curator, build_system_prompt, build_user_message, select_candidates,
)
from .images import clean_searches, screenshot_link
from .fetch import Article, default_get, fetch_all, iso


@dataclass
class Paths:
    root: Path

    @property
    def topics(self) -> Path:
        return self.root / "topics.yaml"

    @property
    def sources(self) -> Path:
        return self.root / "sources.yaml"

    @property
    def settings(self) -> Path:
        return self.root / "settings.yaml"

    @property
    def prompt(self) -> Path:
        return self.root / "prompts" / "curator.md"

    @property
    def articles(self) -> Path:
        return self.root / "site" / "data" / "articles.json"

    @property
    def picks(self) -> Path:
        return self.root / "site" / "data" / "picks.json"

    @property
    def meta(self) -> Path:
        return self.root / "site" / "data" / "meta.json"


@dataclass
class Context:
    categories: list[Category]
    settings: Settings
    template: str
    articles: list[Article]
    fetched: list[Article]
    feed_errors: list[str]
    runs: list[dict]
    previous: list[dict]


def prepare(paths: Paths, now: datetime, http_get=default_get) -> Context:
    categories = load_categories(paths.topics)
    sources = load_sources(paths.sources, categories)
    settings = load_settings(paths.settings)
    fetched, feed_errors = fetch_all(sources, now, settings, http_get=http_get)
    articles = store.merge_articles(store.load_articles(paths.articles), fetched, now, settings.window_hours)
    runs = store.load_runs(paths.picks)
    return Context(categories, settings, paths.prompt.read_text(), articles, fetched, feed_errors,
                   runs, store.recent_picks(runs, now))


def curate_all(ctx: Context, curator: Curator, now: datetime) -> dict[str, dict]:
    by_id = {a.id: a for a in ctx.articles}
    picked_ids = {p["article_id"] for p in ctx.previous}
    this_run: list[dict] = []
    result: dict[str, dict] = {}
    for cat in ctx.categories:
        candidates = [
            a for a in select_candidates(ctx.articles, cat.id, ctx.settings.per_source_cap) if a.id not in picked_ids
        ]
        if not candidates:
            result[cat.id] = {"status": "no_candidates", "error": None, "picks": [], "usage": None}
            continue
        try:
            raw, usage = curator(
                build_system_prompt(ctx.template, cat),
                build_user_message(candidates, ctx.previous + this_run, now),
            )
        except CurationError as e:
            result[cat.id] = {"status": "curation_failed", "error": str(e), "picks": [], "usage": None}
            continue
        picks = []
        for p in validate_picks(raw, {a.id for a in candidates}, picked_ids, cat.max_picks):
            a = by_id[p["article_id"]]
            picks.append({
                "article_id": a.id, "title": a.title, "url": a.url, "source": a.source,
                "published_at": iso(a.published_at), "post": p["post"].strip(), "reason": p["reason"].strip(),
                "card_text": (p.get("card_text") or "").strip(), "image_url": a.image_url,
                "flags": check_post(p["post"], ctx.settings) + check_card(p.get("card_text", "")),
                "image_searches": clean_searches(p.get("image_searches")),
                "screenshot_idea": screenshot_link(p.get("screenshot_idea")),
            })
            picked_ids.add(a.id)
            this_run.append({**picks[-1], "category": cat.id})
        result[cat.id] = {"status": "ok", "error": None, "picks": picks, "usage": usage}
    return result


def total_usage(result: dict[str, dict]) -> dict:
    total = {k: 0 for k in USAGE_KEYS}
    total["cost_usd_equiv"] = 0.0
    for r in result.values():
        for k in total:
            total[k] += (r.get("usage") or {}).get(k, 0)
    total["cost_usd_equiv"] = round(total["cost_usd_equiv"], 6)
    return total


def run(paths: Paths, now: datetime, dry_run: bool, curator: Curator, http_get=default_get,
        out: TextIO = sys.stdout) -> int:
    ctx = prepare(paths, now, http_get)
    result = curate_all(ctx, curator, now)
    totals = total_usage(result)
    _print_summary(out, now, dry_run, ctx.categories, result, ctx.fetched, ctx.feed_errors, totals)

    failed = any(r["status"] == "curation_failed" for r in result.values())
    if dry_run:
        return 1 if failed else 0

    store.save_articles(paths.articles, ctx.articles)
    run_record = {"run_at": iso(now), "categories": result, "usage_total": totals}
    store.save_runs(paths.picks, store.append_run(ctx.runs, run_record, now, ctx.settings.picks_retention_days))
    store.save_meta(paths.meta, ctx.categories, now, ctx.feed_errors,
                    card={"handle": ctx.settings.card_handle, "tagline": ctx.settings.card_tagline})
    return 1 if failed else 0


def fmt_tokens(u: dict) -> str:
    return (f"tokens: in {u['input_tokens']} + cache-write {u['cache_creation_input_tokens']} "
            f"+ cache-read {u['cache_read_input_tokens']}, out {u['output_tokens']} "
            f"(thinking {u['thinking_tokens']}) ≈${u['cost_usd_equiv']:.4f} API-equivalent")


def _print_summary(out, now, dry_run, categories, result, fetched, feed_errors, totals) -> None:
    w = lambda s="": print(s, file=out)  # noqa: E731
    w(f"{'DRY RUN — nothing will be written' if dry_run else 'Run'} at {iso(now)}")
    w(f"Fetched {len(fetched)} articles; {len(feed_errors)} feed error(s).")
    for err in feed_errors:
        w(f"  ! {err}")
    for cat in categories:
        r = result[cat.id]
        w()
        w(f"== {cat.name} [{r['status']}] ==")
        if r["error"]:
            w(f"  error: {r['error']}")
        if r.get("usage"):
            w(f"  [{r['usage']['model']}] {fmt_tokens(r['usage'])}")
        for p in r["picks"]:
            w(f"  • {p['post']}")
            w(f"    ({len(p['post'])} chars) {p['source']} · {p['published_at']} · {p['title']}")
            if p["flags"]:
                w(f"    ⚠ flags: {', '.join(p['flags'])}")
            w(f"    why: {p['reason']}")
    w()
    w(f"TOTAL {fmt_tokens(totals)}")
