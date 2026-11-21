import json
import subprocess
from types import SimpleNamespace

import pytest

from newsbot.config import Settings
from newsbot.curate import CurationError, claude_code_curator, make_curator

S = Settings("haiku", "medium", 15, 24, 30, 280, [], 15, backend="claude-code")
PICKS = {"picks": [{"article_id": "a1", "post": "p", "reason": "r"}]}
USAGE = {"input_tokens": 2, "cache_creation_input_tokens": 1294, "cache_read_input_tokens": 10,
         "output_tokens": 348, "output_tokens_details": {"thinking_tokens": 190}}


def cli_output(**over):
    d = {"type": "result", "is_error": False, "structured_output": PICKS, "usage": USAGE,
         "modelUsage": {"claude-haiku-5-5": {}}, "total_cost_usd": 0.0004}
    d.update(over)
    return json.dumps(d)


class Runner:
    def __init__(self, stdout=None, returncode=0, exc=None):
        self.stdout = cli_output() if stdout is None else stdout
        self.returncode, self.exc, self.calls = returncode, exc, []

    def __call__(self, argv, **kw):
        self.calls.append((argv, kw))
        if self.exc:
            raise self.exc
        return SimpleNamespace(returncode=self.returncode, stdout=self.stdout, stderr="err text")


def test_cli_builds_expected_command():
    r = Runner()
    claude_code_curator(S, runner=r)("SYS", "USER MSG")
    argv, kw = r.calls[0]
    assert argv[:2] == ["claude", "-p"]
    for flag, val in [("--model", "haiku"), ("--tools", ""), ("--output-format", "json"),
                      ("--system-prompt", "SYS"), ("--setting-sources", "")]:
        assert argv[argv.index(flag) + 1] == val
    assert "--json-schema" in argv and "--no-session-persistence" in argv and "--strict-mcp-config" in argv
    assert json.loads(argv[argv.index("--json-schema") + 1])["properties"]["picks"]
    assert kw["input"] == "USER MSG" and kw["timeout"] == 300


def test_cli_parses_structured_output_and_usage():
    picks, usage = claude_code_curator(S, runner=Runner())("s", "u")
    assert picks == PICKS["picks"]
    assert usage == {"model": "claude-haiku-5-5", "input_tokens": 2, "cache_creation_input_tokens": 1294,
                     "cache_read_input_tokens": 10, "output_tokens": 348, "thinking_tokens": 190,
                     "cost_usd_equiv": 0.0004}


def test_cli_is_error_raises():
    with pytest.raises(CurationError, match="usage limit"):
        claude_code_curator(S, runner=Runner(cli_output(is_error=True, result="usage limit reached")))("s", "u")


def test_cli_nonzero_exit_raises():
    with pytest.raises(CurationError):
        claude_code_curator(S, runner=Runner(stdout="", returncode=1))("s", "u")


def test_cli_missing_structured_output_raises():
    with pytest.raises(CurationError):
        claude_code_curator(S, runner=Runner(cli_output(structured_output=None, result="I can't help")))("s", "u")


def test_cli_bad_schema_raises():
    with pytest.raises(CurationError):
        claude_code_curator(S, runner=Runner(cli_output(structured_output={"picks": [{"x": 1}]})))("s", "u")


def test_cli_timeout_raises():
    with pytest.raises(CurationError, match="timed out"):
        claude_code_curator(S, runner=Runner(exc=subprocess.TimeoutExpired("claude", 300)))("s", "u")


def test_cli_missing_binary_raises():
    with pytest.raises(CurationError, match="not found"):
        claude_code_curator(S, runner=Runner(exc=FileNotFoundError()))("s", "u")


def test_usage_defaults_to_zero():
    out = json.dumps({"is_error": False, "structured_output": PICKS})
    _, usage = claude_code_curator(S, runner=Runner(out))("s", "u")
    assert usage["output_tokens"] == 0 and usage["thinking_tokens"] == 0 and usage["model"] == "haiku"


def test_make_curator_model_override(monkeypatch):
    r = Runner()
    import newsbot.curate as c
    monkeypatch.setattr(c.subprocess, "run", r)
    make_curator(S, model_override="sonnet")("s", "u")
    argv = r.calls[0][0]
    assert argv[argv.index("--model") + 1] == "sonnet"
