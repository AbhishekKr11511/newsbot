import io
import json
import re
import shutil
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from newsbot.curate import CurationError
from newsbot.run import Paths, run

ROOT = Path(__file__).resolve().parent.parent
FIX = Path(__file__).parent / "fixtures"
NOW = datetime(2026, 11, 18, 12, 0, tzinfo=UTC)

SOURCES = """
- name: Chips
  url: https://chips.test/rss
  category: trending
- name: Games
  url: https://games.test/rss
  category: gaming
- name: Reuters
  url: https://reuters.test/rss
  category: tech-ai
  strip_title_suffix: " - Reuters"
"""


def http_get(url, timeout):
    return (FIX / ("google_news.xml" if "reuters" in url else "rss_basic.xml")).read_bytes()


@pytest.fixture
def root(tmp_path):
    for name in ("topics.yaml", "settings.yaml"):
        shutil.copy(ROOT / name, tmp_path / name)
    (tmp_path / "prompts").mkdir()
    shutil.copy(ROOT / "prompts" / "curator.md", tmp_path / "prompts" / "curator.md")
    (tmp_path / "sources.yaml").write_text(SOURCES)
    return tmp_path


class FakeClient:
    """Fake curator: picks the first candidate id; optional post text; can fail for one category."""

    def __init__(self, post="Nvidia made $35B. Shocking.", fail_category=None, card="$35B", extra=None):
        self.prompts = []
        self.post, self.fail_category, self.card, self.extra = post, fail_category, card, extra or {}

    def __call__(self, system, user):
        self.prompts.append((system, user))
        if self.fail_category and f"This category: {self.fail_category}" in system:
            raise CurationError("boom")
        cand = user.split("Candidates:", 1)[1]
        ids = re.findall(r"^id: (\S+)$", cand, re.M)
        picks = [{"article_id": ids[0], "post": self.post, "reason": "r", "card_text": self.card, **self.extra}] if ids else []
        usage = {"model": "claude-haiku-5-5", "input_tokens": 100, "cache_creation_input_tokens": 0,
                 "cache_read_input_tokens": 0, "output_tokens": 10, "thinking_tokens": 4, "cost_usd_equiv": 0.001}
        return picks, usage


def data(root, name):
    return json.loads((root / "site" / "data" / f"{name}.json").read_text())


def test_dry_run_writes_nothing(root):
    out = io.StringIO()
    code = run(Paths(root), NOW, True, FakeClient(), http_get=http_get, out=out)
    assert code == 0
    assert not (root / "site" / "data").exists() or not any((root / "site" / "data").glob("*.json"))
    assert "Nvidia made $35B. Shocking." in out.getvalue()
    assert "DRY RUN" in out.getvalue()


def test_live_run_writes_three_files(root):
    assert run(Paths(root), NOW, False, FakeClient(), http_get=http_get, out=io.StringIO()) == 0
    runs = data(root, "picks")
    assert len(runs) == 1
    assert set(runs[0]["categories"]) == {"gaming", "tech-ai", "trending"}
    pick = runs[0]["categories"]["tech-ai"]["picks"][0]
    assert pick["title"] == "TSMC raises capex to $42 billion"
    assert {"article_id", "title", "url", "source", "published_at", "post", "reason", "flags"} <= set(pick)
    assert len(data(root, "articles")) > 0
    assert data(root, "meta")["categories"][0]["id"] == "gaming"


def test_empty_category_skips_claude(root):
    client = FakeClient()
    run(Paths(root), NOW, False, client, http_get=http_get, out=io.StringIO())
    assert data(root, "picks")[0]["categories"]["gaming"]["status"] == "no_candidates"
    assert not any("This category: Gaming" in s for s, _ in client.prompts)


def test_failed_category_does_not_stop_others(root):
    code = run(Paths(root), NOW, False, FakeClient(fail_category="Trending"), http_get=http_get, out=io.StringIO())
    cats = data(root, "picks")[0]["categories"]
    assert code == 1
    assert cats["trending"]["status"] == "curation_failed" and "boom" in cats["trending"]["error"]
    assert cats["tech-ai"]["status"] == "ok"


def test_same_article_not_picked_twice_in_one_run(root):
    # semis and gaming feeds serve the same file -> same URLs -> dedupe means only one category sees them
    run(Paths(root), NOW, False, FakeClient(), http_get=http_get, out=io.StringIO())
    cats = data(root, "picks")[0]["categories"]
    ids = [p["article_id"] for c in cats.values() for p in c["picks"]]
    assert len(ids) == len(set(ids))


def test_second_run_excludes_previous_picks(root):
    run(Paths(root), NOW, False, FakeClient(), http_get=http_get, out=io.StringIO())
    first = {p["article_id"] for c in data(root, "picks")[0]["categories"].values() for p in c["picks"]}
    client = FakeClient()
    run(Paths(root), NOW + timedelta(hours=4), False, client, http_get=http_get, out=io.StringIO())
    for _, user in client.prompts:
        cand = user.split("Candidates:", 1)[1]
        assert not any(f"id: {i}" in cand for i in first)
    assert len(data(root, "picks")) == 2


def test_flags_attached(root):
    run(Paths(root), NOW, False, FakeClient(post="Chips! #AI"), http_get=http_get, out=io.StringIO())
    assert "hashtag" in data(root, "picks")[0]["categories"]["tech-ai"]["picks"][0]["flags"]


def test_usage_recorded_per_category_and_total(root):
    run(Paths(root), NOW, False, FakeClient(), http_get=http_get, out=io.StringIO())
    r = data(root, "picks")[0]
    called = [c for c in r["categories"].values() if c["usage"]]
    assert called and all(c["usage"]["output_tokens"] == 10 for c in called)
    assert r["categories"]["gaming"]["usage"] is None
    assert r["usage_total"]["output_tokens"] == 10 * len(called)
    assert r["usage_total"]["input_tokens"] == 100 * len(called)


def test_summary_prints_tokens(root):
    out = io.StringIO()
    run(Paths(root), NOW, True, FakeClient(), http_get=http_get, out=out)
    assert "tokens" in out.getvalue()


def test_pick_has_card_text_and_image_url(root):
    run(Paths(root), NOW, False, FakeClient(card="x" * 70), http_get=http_get, out=io.StringIO())
    pick = data(root, "picks")[0]["categories"]["tech-ai"]["picks"][0]
    assert pick["card_text"] == "x" * 70
    assert "image_url" in pick
    assert "card_too_long" in pick["flags"]
    assert data(root, "meta")["card"]["handle"].startswith("@")


def test_pick_has_image_fields(root):
    extra = {"image_searches": [{"source": "steam", "query": " GTA 6 "}, {"source": "pexels", "query": "x"}],
             "screenshot_idea": {"text": "Metacritic score page", "search": "GTA 6 metacritic"}}
    run(Paths(root), NOW, False, FakeClient(extra=extra), http_get=http_get, out=io.StringIO())
    pick = data(root, "picks")[0]["categories"]["tech-ai"]["picks"][0]
    assert pick["image_searches"] == [{"source": "steam", "query": "GTA 6"}]
    assert pick["screenshot_idea"] == {"text": "Metacritic score page",
                                       "url": "https://www.google.com/search?q=GTA+6+metacritic"}


def test_old_fake_pick_without_image_fields(root):
    run(Paths(root), NOW, False, FakeClient(), http_get=http_get, out=io.StringIO())
    pick = data(root, "picks")[0]["categories"]["tech-ai"]["picks"][0]
    assert pick["image_searches"] == [] and pick["screenshot_idea"] is None


def test_image_finder_called_with_all_picks(root):
    got = []

    def finder(picks):
        got.extend(picks)
        for p in picks:
            p["images"] = [{"url": "https://i.test/a.jpg", "thumb": "https://i.test/a.jpg", "page_url": "https://i.test",
                            "source": "steam", "credit": "c", "license": "l", "score": 9}]

    run(Paths(root), NOW, False, FakeClient(), http_get=http_get, out=io.StringIO(), image_finder=finder)
    saved = [p for c in data(root, "picks")[0]["categories"].values() for p in c["picks"]]
    assert len(got) == len(saved) >= 2
    assert all(p["images"][0]["score"] == 9 for p in saved)


def test_image_finder_crash_does_not_fail_run(root):
    def finder(picks):
        raise RuntimeError("ollama exploded")

    code = run(Paths(root), NOW, False, FakeClient(), http_get=http_get, out=io.StringIO(), image_finder=finder)
    assert code == 0
    assert data(root, "picks")[0]["categories"]["tech-ai"]["picks"]


def test_summary_prints_images_line(root):
    extra = {"screenshot_idea": {"text": "Metacritic page", "search": "gta metacritic"}}

    def finder(picks):
        for p in picks:
            p["images"] = [{"source": "wikimedia", "score": 9}, {"source": "wikimedia", "score": 6},
                           {"source": "steam", "score": 9}]

    out = io.StringIO()
    run(Paths(root), NOW, True, FakeClient(extra=extra), http_get=http_get, out=out, image_finder=finder)
    text = out.getvalue()
    assert "images: 3 ranked (wikimedia 2, steam 1)" in text
    assert "screenshot: Metacritic page" in text


def test_summary_unranked_and_none(root):
    def finder(picks):
        picks[0]["images"] = [{"source": "steam", "score": None}]
        for p in picks[1:]:
            p["images"] = []

    out = io.StringIO()
    run(Paths(root), NOW, True, FakeClient(), http_get=http_get, out=out, image_finder=finder)
    assert "images: 1 unranked (steam 1)" in out.getvalue()
    assert "images: none" in out.getvalue()
