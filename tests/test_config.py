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


def test_load_settings_image_defaults(tmp_path):
    p = tmp_path / "s.yaml"
    p.write_text("model: haiku\n")
    im = load_settings(p).images
    assert (im.keep, im.max_scored, im.min_score, im.budget_s) == (4, 8, 5, 300)
    assert im.enabled is True
    assert im.ollama_model == "gemma3:4b"
    assert im.ollama_url == "http://localhost:11434"
    assert im.sources == ["wikimedia", "steam", "openverse"]


def test_load_settings_image_overrides(tmp_path):
    p = tmp_path / "s.yaml"
    p.write_text("model: haiku\nimages:\n  keep: 2\n  enabled: false\n")
    im = load_settings(p).images
    assert im.keep == 2 and im.enabled is False and im.max_scored == 8


def test_load_settings_unknown_image_source(tmp_path):
    p = tmp_path / "s.yaml"
    p.write_text("model: haiku\nimages:\n  sources: [pexels]\n")
    with pytest.raises(ConfigError):
        load_settings(p)


def test_real_settings_has_image_block():
    assert load_settings(ROOT / "settings.yaml").images.sources == ["wikimedia", "steam", "openverse"]


# ---- regression: a mistyped images: block (M1) ---------------------------------

@pytest.mark.parametrize("block", ["images:\n  keep: five\n", "images:\n  budget_s: [1]\n", "images: 7\n"])
def test_bad_image_values_give_clear_config_error(tmp_path, block):
    p = tmp_path / "s.yaml"
    p.write_text("model: haiku\n" + block)
    with pytest.raises(ConfigError, match="images"):
        load_settings(p)


def test_image_sources_as_single_string(tmp_path):
    p = tmp_path / "s.yaml"
    p.write_text("model: haiku\nimages:\n  sources: wikimedia\n")
    assert load_settings(p).images.sources == ["wikimedia"]


@pytest.mark.parametrize("value", ['"no"', '"yes"', "1"])
def test_image_enabled_must_be_true_or_false(tmp_path, value):
    p = tmp_path / "s.yaml"
    p.write_text(f"model: haiku\nimages:\n  enabled: {value}\n")
    with pytest.raises(ConfigError, match="enabled"):
        load_settings(p)


@pytest.mark.parametrize("field", ["keep", "max_scored", "budget_s"])
def test_image_counts_must_be_positive(tmp_path, field):
    p = tmp_path / "s.yaml"
    p.write_text(f"model: haiku\nimages:\n  {field}: 0\n")
    with pytest.raises(ConfigError, match=field):
        load_settings(p)


def test_image_min_score_range(tmp_path):
    p = tmp_path / "s.yaml"
    p.write_text("model: haiku\nimages:\n  min_score: 11\n")
    with pytest.raises(ConfigError, match="min_score"):
        load_settings(p)
