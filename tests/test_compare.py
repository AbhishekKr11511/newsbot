import importlib.util
from pathlib import Path

from newsbot.run import Paths
from tests.test_run import NOW, FakeClient, http_get, root  # noqa: F401  (root is a fixture)

spec = importlib.util.spec_from_file_location(
    "compare_models", Path(__file__).resolve().parent.parent / "scripts" / "compare_models.py")
compare_models = importlib.util.module_from_spec(spec)
spec.loader.exec_module(compare_models)


def test_compare_runs_same_candidates_through_each_model(root):
    a, b = FakeClient(post="haiku draft"), FakeClient(post="sonnet draft")
    compare_models.compare(Paths(root), NOW, {"haiku": a, "sonnet": b}, http_get=http_get)
    cands = lambda c: [(sys_, user.split("Candidates:", 1)[1]) for sys_, user in c.prompts]  # noqa: E731
    assert a.prompts and cands(a) == cands(b)


def test_compare_markdown_has_table_and_drafts(root):
    md = compare_models.compare(Paths(root), NOW, {"haiku": FakeClient(post="haiku draft"),
                                                   "sonnet": FakeClient(post="sonnet draft")}, http_get=http_get)
    assert "| haiku |" in md and "| sonnet |" in md
    assert "haiku draft" in md and "sonnet draft" in md
    assert "### Tech & AI drama" in md


def test_compare_writes_nothing_to_site_data(root):
    compare_models.compare(Paths(root), NOW, {"haiku": FakeClient()}, http_get=http_get)
    assert not (root / "site" / "data").exists()
