import sys

from newsbot import __main__ as cli


def setup(monkeypatch, tmp_path, settings_text):
    monkeypatch.chdir(tmp_path)  # no .env here
    (tmp_path / "settings.yaml").write_text(settings_text)
    monkeypatch.setattr(sys, "argv", ["newsbot", "--dry-run"])


def test_missing_claude_cli_exits_with_message(monkeypatch, capsys, tmp_path):
    setup(monkeypatch, tmp_path, "backend: claude-code\nmodel: haiku\n")
    monkeypatch.setattr(cli.shutil, "which", lambda name: None)
    assert cli.main() == 2
    assert "claude" in capsys.readouterr().err


def test_api_backend_missing_key_exits_with_message(monkeypatch, capsys, tmp_path):
    setup(monkeypatch, tmp_path, "backend: api\nmodel: claude-haiku-5-5\n")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert cli.main() == 2
    assert "ANTHROPIC_API_KEY" in capsys.readouterr().err
