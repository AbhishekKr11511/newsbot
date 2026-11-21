import io
import json
import re
import shutil
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

from newsbot.curate import CurationError, CurationResult, Pick
from newsbot.run import Paths, run

ROOT = Path(__file__).resolve().parent.parent
FIX = Path(__file__).parent / "fixtures"
NOW = datetime(2026, 11, 18, 12, 0, tzinfo=UTC)

SOURCES = """
- name: Chips
  url: https://chips.test/rss
  category: semis
- name: Games
  url: https://games.test/rss
  category: gaming
- name: Reuters
  url: https://reuters.test/rss
  category: ai-bigtech
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
    """Picks the first candidate id; optional post text; can fail for one category."""

    def __init__(self, post="Nvidia made $35B. Shocking.", fail_category=None):
        self.prompts = []
        outer = self

        class Messages:
            def parse(self, system, messages, **kw):
                user = messages[0]["content"]
                outer.prompts.append((system, user))
                if fail_category and f"This category: {fail_category}" in system:
                    raise CurationError("boom")
                cand = user.split("Candidates:", 1)[1]
                ids = re.findall(r"^id: (\S+)$", cand, re.M)
                picks = [Pick(article_id=ids[0], post=post, reason="r")] if ids else []
                return SimpleNamespace(stop_reason="end_turn", parsed_output=CurationResult(picks=picks))

        self.beta = SimpleNamespace(messages=Messages())


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
    assert set(runs[0]["categories"]) == {"ai-bigtech", "semis", "gaming", "india-tech", "world-markets"}
    pick = runs[0]["categories"]["ai-bigtech"]["picks"][0]
    assert pick["title"] == "TSMC raises capex to $42 billion"
    assert {"article_id", "title", "url", "source", "published_at", "post", "reason", "flags"} <= set(pick)
    assert len(data(root, "articles")) > 0
    assert data(root, "meta")["categories"][0]["id"] == "ai-bigtech"


def test_empty_category_skips_claude(root):
    client = FakeClient()
    run(Paths(root), NOW, False, client, http_get=http_get, out=io.StringIO())
    assert data(root, "picks")[0]["categories"]["india-tech"]["status"] == "no_candidates"
    assert not any("This category: Indian Tech" in s for s, _ in client.prompts)


def test_failed_category_does_not_stop_others(root):
    code = run(Paths(root), NOW, False, FakeClient(fail_category="Semiconductors"), http_get=http_get, out=io.StringIO())
    cats = data(root, "picks")[0]["categories"]
    assert code == 1
    assert cats["semis"]["status"] == "curation_failed" and "boom" in cats["semis"]["error"]
    assert cats["ai-bigtech"]["status"] == "ok"


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
    assert "hashtag" in data(root, "picks")[0]["categories"]["ai-bigtech"]["picks"][0]["flags"]
