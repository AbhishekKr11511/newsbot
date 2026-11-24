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
    def pick(i, post, reason, flags=(), card=None, images=None, shot=None):
        d = {**{k: articles[i][k] for k in ("title", "url", "source", "published_at", "image_url")},
             "article_id": articles[i]["id"], "post": post, "reason": reason, "flags": list(flags)}
        if card is not None:
            d["card_text"] = card
        if images is not None:
            d["images"] = images
        if shot is not None:
            d["screenshot_idea"] = shot
        return d

    def img(source, url, credit, license, score, thumb=None, page=None):
        return {"url": url, "thumb": thumb or url, "page_url": page or url, "source": source,
                "credit": credit, "license": license, "score": score}

    steam = "https://shared.akamai.steamstatic.com/store_item_assets/steam/apps/3240220/"
    shot1 = steam + "d61184a98c1cf2db2b08b2999c04b0519e3615bb/ss_d61184a98c1cf2db2b08b2999c04b0519e3615bb."
    nadella = "https://upload.wikimedia.org/wikipedia/commons/7/78/MS-Exec-Nadella-Satya-2017-08-31-22_%28cropped%29.jpg"
    ranked = [
        img("steam", steam + "header.jpg", "Official art · Steam", "Promotional", 9, page="https://store.steampowered.com/app/3240220/"),
        img("steam", shot1 + "1920x1080.jpg", "Official art · Steam", "Promotional", 9, thumb=shot1 + "600x338.jpg"),
        img("wikimedia", nadella, "Brian Smale and Microsoft", "CC BY-SA 4.0", 6),
        img("openverse", "https://live.staticflickr.com/3186/2759159448_17455a0fb2_b.jpg",
            "17° Server Room @ Work by Leonardo Rizzi (flickr)", "CC BY-SA 2.0", 6,
            page="https://www.flickr.com/photos/29479498@N05/2759159448"),
    ]
    unranked = [{**ranked[2], "score": None}, {**ranked[3], "score": None}]
    shot = {"text": "Metacritic user score page for GTA V Enhanced",
            "url": "https://www.google.com/search?q=GTA+V+Enhanced+metacritic+user+score"}
    runs = [{
        "run_at": iso(now - timedelta(minutes=10)),
        "categories": {
            "ai-bigtech": {"status": "ok", "error": None, "picks": [pick(6, "OpenAI has signed a deal for 10 gigawatts of power to run its AI models.\n\nThat's roughly what 8 million homes use, and critics are asking who pays the bill.", "AI power demand story", card="10 gigawatts for a chatbot", images=ranked, shot=shot)]},
            "semis": {"status": "ok", "error": None, "picks": [pick(0, "$42 billion in capex, which is TSMC's way of saying the AI bubble isn't popping on their watch.", "Signals sustained AI chip demand", card="$42B capex for 2027"),
                                                              pick(1, "Nvidia ships samples again. Hold the champagne. #chips", "Roadmap on schedule", ["hashtag"])]},
            "gaming": {"status": "ok", "error": None, "picks": [pick(2, "Long headline test.", "wrap test")]},
            "india-tech": {"status": "ok", "error": None, "picks": [pick(5, "Zepto wants $1.2B from public markets. Ten-minute delivery, ten-year path to profit.", "Big Indian IPO", card="$1.2B IPO for 10-minute delivery", images=unranked)]},
            "world-markets": {"status": "no_candidates", "error": None, "picks": []},
        }}]
    (out / "articles.json").write_text(json.dumps(articles, indent=1))
    (out / "picks.json").write_text(json.dumps(runs, indent=1))
    (out / "meta.json").write_text(json.dumps({"last_run_at": runs[0]["run_at"],
                                               "categories": [{"id": a, "name": b} for a, b in cats],
                                               "feed_errors": [], "card": {"handle": "@yourhandle", "tagline": "dry takes on tech"}}, indent=1))


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "site/data")
