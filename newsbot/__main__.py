"""CLI: python -m newsbot [--dry-run] [--model haiku|sonnet] [--no-images]"""
from __future__ import annotations

import argparse
import logging
import os
import shutil
import sys
from datetime import UTC, datetime
from functools import partial
from pathlib import Path

from dotenv import load_dotenv

from .config import load_settings
from .curate import make_curator
from .images import find_images, ollama_ranker
from .run import Paths, run


def main() -> int:
    load_dotenv(Path.cwd() / ".env")
    parser = argparse.ArgumentParser(prog="newsbot", description="Fetch, curate and draft posts.")
    parser.add_argument("--dry-run", action="store_true", help="print drafts, write nothing")
    parser.add_argument("--model", help="override settings.yaml model (e.g. haiku, sonnet)")
    parser.add_argument("--no-images", action="store_true", help="skip the image finder")
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
    image_finder = None
    if settings.images.enabled and not args.no_images:
        image_finder = partial(find_images, cfg=settings.images, fetch_timeout=settings.fetch_timeout_s,
                               ranker=ollama_ranker(settings.images))
    return run(paths, datetime.now(UTC), dry_run, make_curator(settings, args.model), image_finder=image_finder)


if __name__ == "__main__":
    sys.exit(main())
