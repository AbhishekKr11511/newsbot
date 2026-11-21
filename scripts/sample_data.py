"""Write fake site data (times relative to now) for previewing the page.

Usage: python scripts/sample_data.py site/data
"""
import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path


def iso(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def main(out_dir: str) -> None:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    now = datetime.now(UTC).replace(microsecond=0)
    cats = [("ai-bigtech", "AI & Big Tech"), ("semis", "Semiconductors"), ("gaming", "Gaming"),
            ("india-tech", "Indian Tech & Startups"), ("world-markets", "World & Markets")]
    rows = [
        ("semis", "Reuters", "TSMC raises 2027 capex to $42 billion", 1),
        ("semis", "Reuters", "<img src=x onerror=alert(1)> Nvidia ships Rubin samples", 2),
        ("gaming", "PC Gamer", "A very long headline " * 9 + "end", 2),
        ("gaming", "IGN", "Microsoft raises Game Pass Ultimate to $22.99", 3),
        ("gaming", "Kotaku", "Ubisoft confirms 400 more layoffs", 5),
        ("india-tech", "Inc42", "Zepto files for $1.2B IPO", 4),
        ("ai-bigtech", "TechCrunch", "OpenAI signs 10GW power deal", 6),
        ("world-markets", "BBC News", "Rupee hits record low against dollar", 7),
    ]
    articles = [{"id": f"id{i}", "title": t, "url": f"https://example.com/{i}", "source": s, "category": c,
                 "published_at": iso(now - timedelta(hours=h)), "summary": "Sample summary.",
                 "image_url": "https://picsum.photos/seed/%d/640/360" % i if s != "Reuters" else None}
                for i, (c, s, t, h) in enumerate(rows)]
    def pick(i, post, reason, flags=(), card=None):
        d = {**{k: articles[i][k] for k in ("title", "url", "source", "published_at", "image_url")},
             "article_id": articles[i]["id"], "post": post, "reason": reason, "flags": list(flags)}
        if card is not None:
            d["card_text"] = card
        return d
    runs = [{
        "run_at": iso(now - timedelta(minutes=10)),
        "categories": {
            "ai-bigtech": {"status": "ok", "error": None, "picks": [pick(6, "10 gigawatts. For a chatbot. The grid would like a word.", "AI power demand story", card="10 gigawatts for a chatbot")]},
            "semis": {"status": "ok", "error": None, "picks": [pick(0, "$42 billion in capex, which is TSMC's way of saying the AI bubble isn't popping on their watch.", "Signals sustained AI chip demand", card="$42B capex for 2027"),
                                                              pick(1, "Nvidia ships samples again. Hold the champagne. #chips", "Roadmap on schedule", ["hashtag"])]},
            "gaming": {"status": "ok", "error": None, "picks": [pick(2, "Long headline test.", "wrap test")]},
            "india-tech": {"status": "ok", "error": None, "picks": [pick(5, "Zepto wants $1.2B from public markets. Ten-minute delivery, ten-year path to profit.", "Big Indian IPO", card="$1.2B IPO for 10-minute delivery")]},
            "world-markets": {"status": "no_candidates", "error": None, "picks": []},
        }}]
    (out / "articles.json").write_text(json.dumps(articles, indent=1))
    (out / "picks.json").write_text(json.dumps(runs, indent=1))
    (out / "meta.json").write_text(json.dumps({"last_run_at": runs[0]["run_at"],
                                               "categories": [{"id": a, "name": b} for a, b in cats],
                                               "feed_errors": [], "card": {"handle": "@yourhandle", "tagline": "dry takes on tech"}}, indent=1))


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "site/data")
