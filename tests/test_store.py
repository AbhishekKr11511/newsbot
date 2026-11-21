import json
from datetime import UTC, datetime, timedelta

from newsbot.config import Category
from newsbot.fetch import Article, iso
from newsbot.store import (
    append_run, load_articles, load_runs, merge_articles, recent_picks,
    save_articles, save_meta,
)

NOW = datetime(2026, 11, 18, 12, 0, tzinfo=UTC)


def art(i, hours_ago):
    return Article(f"id{i}", f"T{i}", f"https://x/{i}", "S", "gaming", NOW - timedelta(hours=hours_ago), "s")


def run(hours_ago, picks=None):
    return {"run_at": iso(NOW - timedelta(hours=hours_ago)),
            "categories": {"gaming": {"status": "ok", "error": None, "picks": picks or []}}}


def test_load_missing_files_returns_empty(tmp_path):
    assert load_articles(tmp_path / "a.json") == []
    assert load_runs(tmp_path / "p.json") == []


def test_merge_dedupes_and_prunes():
    existing = [art(1, 25), art(2, 5)]
    newer2 = art(2, 5)
    newer2.title = "updated"
    merged = merge_articles(existing, [newer2, art(3, 1)], NOW, 24)
    assert [a.id for a in merged] == ["id3", "id2"]
    assert merged[1].title == "updated"


def test_articles_roundtrip(tmp_path):
    p = tmp_path / "data" / "articles.json"
    arts = [art(1, 1), art(2, 2)]
    save_articles(p, arts)
    assert load_articles(p) == arts


def test_append_run_prunes_after_retention():
    runs = [run(31 * 24), run(29 * 24)]
    out = append_run(runs, run(0), NOW, 30)
    assert len(out) == 2
    assert out[-1]["run_at"] == iso(NOW)


def test_recent_picks_only_last_24h():
    runs = [run(30, [{"article_id": "old", "post": "p"}]), run(2, [{"article_id": "new", "post": "p"}])]
    picks = recent_picks(runs, NOW)
    assert [p["article_id"] for p in picks] == ["new"]
    assert picks[0]["category"] == "gaming"


def test_save_meta_shape(tmp_path):
    p = tmp_path / "meta.json"
    save_meta(p, [Category("a", "A", 3, "", ""), Category("b", "B", 3, "", "")], NOW, ["X: boom"])
    d = json.loads(p.read_text())
    assert d == {"last_run_at": "2026-11-18T12:00:00Z",
                 "categories": [{"id": "a", "name": "A"}, {"id": "b", "name": "B"}],
                 "feed_errors": ["X: boom"]}


def test_meta_has_card_settings(tmp_path):
    p = tmp_path / "meta.json"
    save_meta(p, [Category("a", "A", 3, "", "")], NOW, [], card={"handle": "@me", "tagline": "t"})
    assert json.loads(p.read_text())["card"] == {"handle": "@me", "tagline": "t"}
