"""Read/write the JSON files in site/data/ that the page renders."""
from __future__ import annotations

import json
import os
from datetime import datetime, timedelta
from pathlib import Path

from .config import Category
from .fetch import Article, iso, parse_iso


def _read(path: Path, default):
    path = Path(path)
    if not path.exists():
        return default
    return json.loads(path.read_text())


def _write(path: Path, data) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=1, ensure_ascii=False))
    os.replace(tmp, path)


def load_articles(path: Path) -> list[Article]:
    return [Article.from_dict(d) for d in _read(path, [])]


def save_articles(path: Path, articles: list[Article]) -> None:
    _write(path, [a.to_dict() for a in articles])


def merge_articles(existing: list[Article], new: list[Article], now: datetime, window_hours: int) -> list[Article]:
    cutoff = now - timedelta(hours=window_hours)
    by_id = {a.id: a for a in existing}
    by_id.update({a.id: a for a in new})
    kept = [a for a in by_id.values() if a.published_at >= cutoff]
    return sorted(kept, key=lambda a: a.published_at, reverse=True)


def load_runs(path: Path) -> list[dict]:
    return _read(path, [])


def save_runs(path: Path, runs: list[dict]) -> None:
    _write(path, runs)


def append_run(runs: list[dict], run: dict, now: datetime, retention_days: int) -> list[dict]:
    cutoff = now - timedelta(days=retention_days)
    return [r for r in runs if parse_iso(r["run_at"]) >= cutoff] + [run]


def recent_picks(runs: list[dict], now: datetime, hours: int = 24) -> list[dict]:
    cutoff = now - timedelta(hours=hours)
    out = []
    for r in runs:
        if parse_iso(r["run_at"]) < cutoff:
            continue
        for cat_id, cat in r.get("categories", {}).items():
            out.extend({**p, "category": cat_id} for p in cat.get("picks", []))
    return out


def save_meta(path: Path, categories: list[Category], last_run_at: datetime, feed_errors: list[str]) -> None:
    _write(path, {
        "last_run_at": iso(last_run_at),
        "categories": [{"id": c.id, "name": c.name} for c in categories],
        "feed_errors": feed_errors,
    })
