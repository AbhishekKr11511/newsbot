"""CLI: python -m newsbot [--dry-run] [--model haiku|sonnet]"""
from __future__ import annotations

import argparse
import logging
import os
import shutil
import sys
from datetime import UTC, datetime
from pathlib import Path

from dotenv import load_dotenv

from .config import load_settings
from .curate import make_curator
from .run import Paths, run


def main() -> int:
    load_dotenv(Path.cwd() / ".env")
    parser = argparse.ArgumentParser(prog="newsbot", description="Fetch, curate and draft posts.")
    parser.add_argument("--dry-run", action="store_true", help="print drafts, write nothing")
    parser.add_argument("--model", help="override settings.yaml model (e.g. haiku, sonnet)")
    args = parser.parse_args()
    dry_run = args.dry_run or os.environ.get("DRY_RUN", "").strip().lower() in ("true", "1")
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")

    paths = Paths(Path.cwd())
    settings = load_settings(paths.settings)
    if settings.backend == "api":
        if not os.environ.get("ANTHROPIC_API_KEY"):
            print("ANTHROPIC_API_KEY is not set. Add it to .env, or switch settings.yaml to backend: claude-code.",
                  file=sys.stderr)
            return 2
    elif not shutil.which("claude"):
        print("The `claude` CLI was not found on PATH. Install Claude Code and log in with your Pro plan.",
              file=sys.stderr)
        return 2
    return run(paths, datetime.now(UTC), dry_run, make_curator(settings, args.model))


if __name__ == "__main__":
    sys.exit(main())
