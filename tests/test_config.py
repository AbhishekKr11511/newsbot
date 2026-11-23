from pathlib import Path

import pytest

from newsbot.config import ConfigError, load_categories, load_settings, load_sources

ROOT = Path(__file__).resolve().parent.parent


def write(tmp_path, text):
    p = tmp_path / "sources.yaml"
    p.write_text(text)
    return p


def cats():
    return load_categories(ROOT / "topics.yaml")


def test_load_categories_reads_three():
    c = cats()
    assert [x.id for x in c] == ["gaming", "tech-ai", "trending"]
    assert [x.max_picks for x in c] == [3, 3, 1]
    assert c[0].name == "Gaming"


def test_unknown_category_raises(tmp_path):
    p = write(tmp_path, "- name: X\n  url: https://x.com/rss\n  category: nope\n")
    with pytest.raises(ConfigError, match="nope"):
        load_sources(p, cats())


def test_missing_url_raises(tmp_path):
    p = write(tmp_path, "- name: X\n  category: gaming\n")
    with pytest.raises(ConfigError):
        load_sources(p, cats())


def test_source_defaults(tmp_path):
    p = write(tmp_path, "- name: X\n  url: https://x.com/rss\n  category: gaming\n")
    (s,) = load_sources(p, cats())
    assert s.kind == "rss"
    assert s.strip_title_suffix is None


def test_load_settings():
    s = load_settings(ROOT / "settings.yaml")
    assert s.effort == "medium"
    assert s.per_source_cap == 15
    assert "masterstroke" in s.banned_words


def test_load_settings_backend():
    s = load_settings(ROOT / "settings.yaml")
    assert s.backend == "claude-code"
    assert s.model == "haiku"


def test_load_settings_card_defaults(tmp_path):
    p = tmp_path / "s.yaml"
    p.write_text("model: haiku\n")
    s = load_settings(p)
    assert s.card_handle == "@yourhandle" and s.card_tagline == ""
    assert load_settings(ROOT / "settings.yaml").card_handle.startswith("@")
