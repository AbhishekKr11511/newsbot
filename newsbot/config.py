"""Load the owner-editable YAML config files."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml


class ConfigError(Exception):
    pass


@dataclass(frozen=True)
class Source:
    name: str
    url: str
    category: str
    kind: str = "rss"
    strip_title_suffix: str | None = None


@dataclass(frozen=True)
class Category:
    id: str
    name: str
    max_picks: int
    covers: str
    skip: str


@dataclass(frozen=True)
class Settings:
    model: str
    effort: str
    per_source_cap: int
    window_hours: int
    picks_retention_days: int
    max_post_chars: int
    banned_words: list[str] = field(default_factory=list)
    fetch_timeout_s: int = 15
    backend: str = "claude-code"  # claude-code | api
    card_handle: str = "@yourhandle"
    card_tagline: str = ""


def _load_list(path: Path) -> list[dict]:
    data = yaml.safe_load(Path(path).read_text()) or []
    if not isinstance(data, list):
        raise ConfigError(f"{path}: expected a list of entries")
    return data


def _require(entry: dict, keys: tuple[str, ...], where: str) -> None:
    missing = [k for k in keys if not entry.get(k)]
    if missing:
        raise ConfigError(f"{where}: missing {', '.join(missing)} in {entry!r}")


def load_categories(path: Path) -> list[Category]:
    out = []
    for e in _load_list(path):
        _require(e, ("id", "name"), str(path))
        out.append(
            Category(
                id=str(e["id"]),
                name=str(e["name"]),
                max_picks=int(e.get("max_picks", 3)),
                covers=str(e.get("covers", "")),
                skip=str(e.get("skip", "")),
            )
        )
    ids = [c.id for c in out]
    if len(ids) != len(set(ids)):
        raise ConfigError(f"{path}: duplicate category ids")
    return out


def load_sources(path: Path, categories: list[Category]) -> list[Source]:
    known = {c.id for c in categories}
    out = []
    for e in _load_list(path):
        _require(e, ("name", "url", "category"), str(path))
        if e["category"] not in known:
            raise ConfigError(f"{path}: source {e['name']!r} has unknown category {e['category']!r}")
        out.append(
            Source(
                name=str(e["name"]),
                url=str(e["url"]),
                category=str(e["category"]),
                kind=str(e.get("kind", "rss")),
                strip_title_suffix=e.get("strip_title_suffix"),
            )
        )
    return out


def load_settings(path: Path) -> Settings:
    d = yaml.safe_load(Path(path).read_text()) or {}
    try:
        return Settings(
            model=str(d["model"]),
            effort=str(d.get("effort", "medium")),
            per_source_cap=int(d.get("per_source_cap", 15)),
            window_hours=int(d.get("window_hours", 24)),
            picks_retention_days=int(d.get("picks_retention_days", 30)),
            max_post_chars=int(d.get("max_post_chars", 280)),
            banned_words=[str(w) for w in d.get("banned_words", [])],
            fetch_timeout_s=int(d.get("fetch_timeout_s", 15)),
            backend=str(d.get("backend", "claude-code")),
            card_handle=str(d.get("card_handle", "@yourhandle")),
            card_tagline=str(d.get("card_tagline") or ""),
        )
    except KeyError as e:
        raise ConfigError(f"{path}: missing {e}") from e
