import sys

from newsbot import __main__ as cli


def test_missing_api_key_exits_with_message(monkeypatch, capsys, tmp_path):
    monkeypatch.chdir(tmp_path)  # no .env here
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setattr(sys, "argv", ["newsbot", "--dry-run"])
    assert cli.main() == 2
    assert "ANTHROPIC_API_KEY" in capsys.readouterr().err
