"""Run scripts/run_and_publish.sh in a throwaway git repo with a fake bot."""
import os
import shutil
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "run_and_publish.sh"

FAKE_BOT = """#!/bin/bash
mkdir -p site/data
date +%s%N > site/data/picks.json
echo "== Gaming [ok] =="
echo "  • first draft"
echo "  • second draft"
exit ${FAKE_EXIT:-0}
"""


def git(repo, *args):
    return subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, check=True).stdout


@pytest.fixture
def repo(tmp_path):
    r = tmp_path / "my repo"  # space on purpose
    (r / "scripts").mkdir(parents=True)
    shutil.copy(SCRIPT, r / "scripts" / "run_and_publish.sh")
    (r / ".venv" / "bin").mkdir(parents=True)
    bot = r / ".venv" / "bin" / "python"
    bot.write_text(FAKE_BOT)
    bot.chmod(0o755)
    (r / ".gitignore").write_text(".venv/\nlogs/\n")
    git(r, "init", "-q", "-b", "main")
    git(r, "config", "user.email", "t@t")
    git(r, "config", "user.name", "t")
    (r / "code.py").write_text("x = 1\n")
    git(r, "add", "-A")
    git(r, "commit", "-qm", "init")
    return r


def run_script(repo, **extra):
    notify = repo.parent / "notify.sh"
    notify.write_text('#!/bin/bash\necho "$1|$2" >> "%s"\n' % (repo.parent / "notes.txt"))
    notify.chmod(0o755)
    env = {"HOME": os.environ["HOME"], "PATH": "/usr/bin:/bin", "DRY_RUN": "false",
           "NEWSBOT_NOTIFY_CMD": str(notify), **extra}
    p = subprocess.run(["/bin/bash", str(repo / "scripts" / "run_and_publish.sh")], cwd=repo, env=env)
    return p.returncode, (repo / "logs" / "run.log").read_text()


def notes(repo):
    f = repo.parent / "notes.txt"
    return f.read_text() if f.exists() else ""


def test_commits_only_site_data(repo):
    (repo / "code.py").write_text("x = 2\n")
    git(repo, "add", "code.py")  # owner's unrelated staged edit
    code, _ = run_script(repo)
    assert code == 0
    files = git(repo, "show", "--name-only", "--format=", "HEAD").split()
    assert files == ["site/data/picks.json"]
    assert "code.py" in git(repo, "diff", "--cached", "--name-only")  # still staged, not committed


def test_skips_commit_when_not_on_main(repo):
    git(repo, "checkout", "-qb", "feature")
    before = git(repo, "rev-parse", "HEAD")
    code, log = run_script(repo)
    assert git(repo, "rev-parse", "HEAD") == before
    assert "not on main" in log


def test_skips_publish_when_pull_fails(repo):
    git(repo, "remote", "add", "origin", str(repo.parent / "does-not-exist.git"))
    before = git(repo, "rev-parse", "HEAD")
    code, log = run_script(repo)
    assert git(repo, "rev-parse", "HEAD") == before
    assert "pull failed" in log
    assert not (repo / ".git" / "rebase-merge").exists()


def test_notifies_draft_count_on_success(repo):
    run_script(repo)
    assert "2 drafts ready" in notes(repo)


def test_notifies_failure(repo):
    code, _ = run_script(repo, FAKE_EXIT="1")
    assert code == 1
    assert "failed" in notes(repo).lower()


def test_notifies_dry_run(repo):
    run_script(repo, DRY_RUN="true")
    n = notes(repo)
    assert "2 drafts" in n and "dry run" in n.lower()
