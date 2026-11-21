"""Run the same headlines through several models and write a side-by-side report.

Usage: python scripts/compare_models.py [--models haiku sonnet]
Writes compare-<date>.md in the project root. Never touches site/data.
"""
from __future__ import annotations

import argparse
import shutil
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402

from newsbot.config import load_settings  # noqa: E402
from newsbot.curate import Curator, make_curator  # noqa: E402
from newsbot.fetch import default_get, iso  # noqa: E402
from newsbot.run import Paths, curate_all, prepare, total_usage  # noqa: E402


def compare(paths: Paths, now: datetime, curators: dict[str, Curator], http_get=default_get) -> str:
    ctx = prepare(paths, now, http_get)  # fetch once; every model sees the same articles
    results = {name: curate_all(ctx, curator, now) for name, curator in curators.items()}

    lines = [
        f"# Model comparison — {iso(now)}",
        "",
        f"{len(ctx.fetched)} articles fetched, {len(ctx.feed_errors)} feed error(s). "
        "Each model got the same candidates (later categories can differ slightly, because each "
        "model's earlier picks are excluded from later categories).",
        "",
        "## Tokens",
        "",
        "| model | input | cache write | cache read | output | thinking | ≈ API $ equiv |",
        "|---|---|---|---|---|---|---|",
    ]
    for name, result in results.items():
        t = total_usage(result)
        lines.append(
            f"| {name} | {t['input_tokens']} | {t['cache_creation_input_tokens']} | {t['cache_read_input_tokens']} "
            f"| {t['output_tokens']} | {t['thinking_tokens']} | {t['cost_usd_equiv']:.4f} |"
        )
    lines += ["", "On the Pro plan you don't pay the $ column; it shows relative size only.", ""]

    for cat in ctx.categories:
        lines += [f"### {cat.name}", ""]
        for name, result in results.items():
            r = result[cat.id]
            lines.append(f"**{name}** — {r['status']}" + (f" ({r['error']})" if r["error"] else ""))
            for p in r["picks"]:
                flags = f" ⚠ {', '.join(p['flags'])}" if p["flags"] else ""
                lines.append(f"- {p['post']}{flags}")
                lines.append(f"  - _{p['source']}: {p['title']}_ — why: {p['reason']}")
            if not r["picks"]:
                lines.append("- (no picks)")
            lines.append("")
    return "\n".join(lines)


def main() -> int:
    load_dotenv(ROOT / ".env")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--models", nargs="+", default=["haiku", "sonnet"])
    args = parser.parse_args()
    paths = Paths(ROOT)
    settings = load_settings(paths.settings)
    if settings.backend != "api" and not shutil.which("claude"):
        print("The `claude` CLI was not found on PATH.", file=sys.stderr)
        return 2
    now = datetime.now(UTC)
    md = compare(paths, now, {m: make_curator(settings, m) for m in args.models})
    out = ROOT / f"compare-{now.strftime('%Y-%m-%d-%H%M')}.md"
    out.write_text(md)
    print(f"Wrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
