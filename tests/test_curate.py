from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import anthropic
import httpx2
import pytest

from newsbot.config import Category, Settings
from newsbot.curate import (
    CurationError, CurationResult, Pick, build_system_prompt, build_user_message,
    curate_category, select_candidates,
)
from newsbot.fetch import Article

NOW = datetime(2026, 11, 18, 12, 0, tzinfo=UTC)
S = Settings("claude-sonnet-5-5", "medium", 15, 24, 30, 280, [], 15)
CAT = Category("gaming", "Gaming", 3, "industry moves", "trailers")


def art(i, source="IGN", category="gaming", hours_ago=1):
    return Article(f"id{source}{i}", f"Title {i}", f"https://x/{source}/{i}", source, category,
                   NOW - timedelta(hours=hours_ago, minutes=i), "summary")


class FakeClient:
    def __init__(self, response=None, exc=None):
        self.calls = []
        outer = self

        class Messages:
            def parse(self, **kw):
                outer.calls.append(kw)
                if exc:
                    raise exc
                return response

        self.beta = SimpleNamespace(messages=Messages())


def ok(picks):
    return SimpleNamespace(stop_reason="end_turn", parsed_output=CurationResult(picks=picks))


def test_select_candidates_caps_per_source():
    arts = [art(i) for i in range(20)] + [art(i, "Kotaku") for i in range(3)] + [art(0, "BBC", "world-markets")]
    out = select_candidates(arts, "gaming", 15)
    assert len(out) == 18
    assert all(a.category == "gaming" for a in out)
    assert [a.published_at for a in out] == sorted((a.published_at for a in out), reverse=True)


def test_system_prompt_fills_placeholders():
    template = "Pick 0-{max_picks}. Cat: {category_name}. Covers: {covers}. Skip: {skip}."
    out = build_system_prompt(template, CAT)
    assert out == "Pick 0-3. Cat: Gaming. Covers: industry moves. Skip: trailers."


def test_real_prompt_file_has_no_leftover_placeholders():
    from pathlib import Path
    template = (Path(__file__).resolve().parent.parent / "prompts" / "curator.md").read_text()
    out = build_system_prompt(template, CAT)
    assert "{" not in out and "Gaming" in out


def test_user_message_includes_ids_and_covered():
    cands = [art(1), art(2)]
    msg = build_user_message(cands, [{"category": "semis", "title": "TSMC capex", "post": "p"}], NOW)
    assert "idIGN1" in msg and "idIGN2" in msg
    assert "TSMC capex" in msg
    assert "Already covered (last 24h):\nnone" in build_user_message(cands, [], NOW)


def test_curate_returns_picks():
    client = FakeClient(ok([Pick(article_id="a", post="p1", reason="r", card_text="c", image_searches=[], screenshot_idea={"text": "", "search": ""}), Pick(article_id="b", post="p2", reason="r", card_text="c", image_searches=[], screenshot_idea={"text": "", "search": ""})]))
    out = curate_category(client, S, "sys", "user")
    assert out == [{"article_id": "a", "post": "p1", "reason": "r", "card_text": "c", "image_searches": [], "screenshot_idea": {"text": "", "search": ""}}, {"article_id": "b", "post": "p2", "reason": "r", "card_text": "c", "image_searches": [], "screenshot_idea": {"text": "", "search": ""}}]


def test_curate_passes_model_and_effort():
    client = FakeClient(ok([]))
    curate_category(client, S, "sys", "user")
    kw = client.calls[0]
    assert kw["model"] == "claude-sonnet-5-5"
    assert kw["output_config"] == {"effort": "medium"}
    assert kw["output_format"] is CurationResult
    assert kw["fallbacks"] == "default"
    assert "temperature" not in kw


def test_refusal_raises_curation_error():
    client = FakeClient(SimpleNamespace(stop_reason="refusal", parsed_output=None))
    with pytest.raises(CurationError, match="refusal"):
        curate_category(client, S, "sys", "user")


def test_max_tokens_raises_curation_error():
    client = FakeClient(SimpleNamespace(stop_reason="max_tokens", parsed_output=None))
    with pytest.raises(CurationError):
        curate_category(client, S, "sys", "user")


def test_api_error_raises_curation_error():
    client = FakeClient(exc=anthropic.APIConnectionError(request=httpx2.Request("POST", "https://x")))
    with pytest.raises(CurationError):
        curate_category(client, S, "sys", "user")


def real_client(stop_reason, text):
    """A real SDK client whose HTTP layer returns a canned Messages response."""
    import json as _json

    def handler(request):
        body = {"id": "msg_1", "type": "message", "role": "assistant", "model": "claude-sonnet-5-5",
                "content": [{"type": "text", "text": text}], "stop_reason": stop_reason,
                "stop_sequence": None, "usage": {"input_tokens": 1, "output_tokens": 1}}
        return httpx2.Response(200, json=body)

    return anthropic.Anthropic(api_key="test", max_retries=0,
                               http_client=httpx2.Client(transport=httpx2.MockTransport(handler)))


def test_real_sdk_refusal_becomes_curation_error():
    with pytest.raises(CurationError):
        curate_category(real_client("refusal", "I can't help with that."), S, "sys", "user")


def test_real_sdk_truncated_json_becomes_curation_error():
    with pytest.raises(CurationError):
        curate_category(real_client("max_tokens", '{"picks": [{"article_id": "a", "po'), S, "sys", "user")


def test_real_sdk_valid_reply_parses():
    text = '{"picks": [{"article_id": "a", "post": "p", "reason": "r", "card_text": "c", "image_searches": [], "screenshot_idea": {"text": "", "search": ""}}]}'
    assert curate_category(real_client("end_turn", text), S, "sys", "user") == [
        {"article_id": "a", "post": "p", "reason": "r", "card_text": "c", "image_searches": [], "screenshot_idea": {"text": "", "search": ""}}]


def test_missing_api_key_becomes_curation_error(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
    client = anthropic.Anthropic(api_key=None, max_retries=0,
                                 http_client=httpx2.Client(transport=httpx2.MockTransport(lambda r: httpx2.Response(500))))
    with pytest.raises(CurationError):
        curate_category(client, S, "sys", "user")
