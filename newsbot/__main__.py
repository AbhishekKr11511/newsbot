"""CLI: python -m newsbot [--dry-run]"""
from __future__ import annotations

import argparse
import logging
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

import anthropic
from dotenv import load_dotenv

from .run import Paths, run


def main() -> int:
    load_dotenv()
    parser = argparse.ArgumentParser(prog="newsbot", description="Fetch, curate and draft posts.")
    parser.add_argument("--dry-run", action="store_true", help="print drafts, write nothing")
    args = parser.parse_args()
    dry_run = args.dry_run or os.environ.get("DRY_RUN", "").strip().lower() in ("true", "1")
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")
    return run(Paths(Path.cwd()), datetime.now(UTC), dry_run, anthropic.Anthropic())


if __name__ == "__main__":
    sys.exit(main())
