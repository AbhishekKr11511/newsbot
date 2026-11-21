"""Check every feed in sources.yaml. Usage: python scripts/check_feeds.py"""
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from newsbot.config import load_categories, load_settings, load_sources  # noqa: E402
from newsbot.fetch import default_get, iso, parse_feed  # noqa: E402


def main() -> int:
    root = Path(__file__).resolve().parent.parent
    cats = load_categories(root / "topics.yaml")
    settings = load_settings(root / "settings.yaml")
    now = datetime.now(UTC)
    failed = 0
    for s in load_sources(root / "sources.yaml", cats):
        try:
            arts = parse_feed(default_get(s.url, settings.fetch_timeout_s), s, now, settings.window_hours)
            newest = iso(arts[0].published_at) if arts else "-"
            print(f"OK   {s.name:<22} {len(arts):>3} items in 24h, newest {newest}")
        except Exception as e:
            failed += 1
            print(f"FAIL {s.name:<22} {type(e).__name__}: {e}"[:160])
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
