"""One bot run: fetch → curate per category → check → store."""
from __future__ import annotations

import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import TextIO

from . import store
from .checks import check_post, validate_picks
from .config import load_categories, load_settings, load_sources
from .curate import CurationError, build_system_prompt, build_user_message, curate_category, select_candidates
from .fetch import default_get, fetch_all, iso


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


def run(paths: Paths, now: datetime, dry_run: bool, client, http_get=default_get, out: TextIO = sys.stdout) -> int:
    categories = load_categories(paths.topics)
    sources = load_sources(paths.sources, categories)
    settings = load_settings(paths.settings)
    template = paths.prompt.read_text()

    fetched, feed_errors = fetch_all(sources, now, settings, http_get=http_get)
    articles = store.merge_articles(store.load_articles(paths.articles), fetched, now, settings.window_hours)
    by_id = {a.id: a for a in articles}
    runs = store.load_runs(paths.picks)
    previous = store.recent_picks(runs, now)
    picked_ids = {p["article_id"] for p in previous}
    this_run: list[dict] = []

    result: dict[str, dict] = {}
    for cat in categories:
        candidates = [
            a for a in select_candidates(articles, cat.id, settings.per_source_cap) if a.id not in picked_ids
        ]
        if not candidates:
            result[cat.id] = {"status": "no_candidates", "error": None, "picks": []}
            continue
        try:
            raw = curate_category(
                client,
                settings,
                build_system_prompt(template, cat),
                build_user_message(candidates, previous + this_run, now),
            )
        except CurationError as e:
            result[cat.id] = {"status": "curation_failed", "error": str(e), "picks": []}
            continue
        picks = []
        for p in validate_picks(raw, {a.id for a in candidates}, picked_ids, cat.max_picks):
            a = by_id[p["article_id"]]
            picks.append({
                "article_id": a.id, "title": a.title, "url": a.url, "source": a.source,
                "published_at": iso(a.published_at), "post": p["post"].strip(), "reason": p["reason"].strip(),
                "flags": check_post(p["post"], settings),
            })
            picked_ids.add(a.id)
            this_run.append({**picks[-1], "category": cat.id})
        result[cat.id] = {"status": "ok", "error": None, "picks": picks}

    _print_summary(out, now, dry_run, categories, result, fetched, feed_errors)

    failed = any(r["status"] == "curation_failed" for r in result.values())
    if dry_run:
        return 1 if failed else 0

    store.save_articles(paths.articles, articles)
    run_record = {"run_at": iso(now), "categories": result}
    store.save_runs(paths.picks, store.append_run(runs, run_record, now, settings.picks_retention_days))
    store.save_meta(paths.meta, categories, now, feed_errors)
    return 1 if failed else 0


def _print_summary(out, now, dry_run, categories, result, fetched, feed_errors) -> None:
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
        for p in r["picks"]:
            w(f"  • {p['post']}")
            w(f"    ({len(p['post'])} chars) {p['source']} · {p['published_at']} · {p['title']}")
            if p["flags"]:
                w(f"    ⚠ flags: {', '.join(p['flags'])}")
            w(f"    why: {p['reason']}")
