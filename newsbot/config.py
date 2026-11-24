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


IMAGE_SOURCES = ("wikimedia", "steam", "openverse")


@dataclass(frozen=True)
class ImageSettings:
    enabled: bool = True
    sources: list[str] = field(default_factory=lambda: list(IMAGE_SOURCES))
    ollama_url: str = "http://localhost:11434"
    ollama_model: str = "gemma3:4b"
    keep: int = 4
    max_scored: int = 8
    min_score: int = 5
    budget_s: int = 300


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
    images: ImageSettings = field(default_factory=ImageSettings)


def _image_int(d: dict, key: str, default: int, path, low: int, high: int | None = None) -> int:
    value = d.get(key, default)
    if isinstance(value, bool) or not isinstance(value, (int, str)):
        raise ConfigError(f"{path}: images.{key} must be a whole number, got {value!r}")
    try:
        n = int(value)
    except ValueError:
        raise ConfigError(f"{path}: images.{key} must be a whole number, got {value!r}") from None
    if n < low or (high is not None and n > high):
        bounds = f"between {low} and {high}" if high is not None else f"at least {low}"
        raise ConfigError(f"{path}: images.{key} must be {bounds}, got {n}")
    return n


def _load_images(d, path) -> ImageSettings:
    if d is None:
        return ImageSettings()
    if not isinstance(d, dict):
        raise ConfigError(f"{path}: images must be a mapping")
    base = ImageSettings()
    enabled = d.get("enabled", base.enabled)
    if not isinstance(enabled, bool):
        raise ConfigError(f"{path}: images.enabled must be true or false (no quotes), got {enabled!r}")
    raw_sources = d.get("sources", base.sources)
    if isinstance(raw_sources, str):
        raw_sources = [raw_sources]
    if not isinstance(raw_sources, list):
        raise ConfigError(f"{path}: images.sources must be a list like [wikimedia, steam, openverse]")
    sources = [str(x).strip() for x in raw_sources]
    unknown = [x for x in sources if x not in IMAGE_SOURCES]
    if unknown:
        raise ConfigError(f"{path}: unknown image source(s) {', '.join(unknown)}; use {', '.join(IMAGE_SOURCES)}")
    return ImageSettings(
        enabled=enabled,
        sources=sources,
        ollama_url=str(d.get("ollama_url", base.ollama_url)).rstrip("/"),
        ollama_model=str(d.get("ollama_model", base.ollama_model)),
        keep=_image_int(d, "keep", base.keep, path, 1),
        max_scored=_image_int(d, "max_scored", base.max_scored, path, 1),
        min_score=_image_int(d, "min_score", base.min_score, path, 0, 10),
        budget_s=_image_int(d, "budget_s", base.budget_s, path, 1),
    )


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
            images=_load_images(d.get("images"), path),
        )
    except KeyError as e:
        raise ConfigError(f"{path}: missing {e}") from e
