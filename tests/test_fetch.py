from datetime import UTC, datetime, timedelta
from pathlib import Path

from newsbot.config import Settings, Source
from newsbot.fetch import Article, article_id, canonicalize_url, fetch_all, parse_feed

FIX = Path(__file__).parent / "fixtures"
NOW = datetime(2026, 11, 18, 12, 0, tzinfo=UTC)
SETTINGS = Settings("m", "medium", 15, 24, 30, 280, [], 15)


def src(name="Basic", category="semis", **kw):
    return Source(name=name, url=f"https://{name.lower()}.test/rss", category=category, **kw)


def parse(fixture, source=None):
    return parse_feed((FIX / fixture).read_bytes(), source or src(), NOW, 24)


def test_canonicalize_strips_tracking():
    assert canonicalize_url("https://Example.com/a?utm_source=x&id=5#top") == "https://example.com/a?id=5"


def test_article_id_stable_across_tracking_params():
    assert article_id("https://example.com/a?utm_medium=rss") == article_id("https://example.com/a")
    assert len(article_id("https://example.com/a")) == 16


def test_parse_basic_rss():
    arts = parse("rss_basic.xml")
    assert len(arts) == 3
    a = arts[0]
    assert a.title == "Nvidia posts record $35B quarter"
    assert a.url == "https://example.com/nvidia"
    assert a.summary == "Revenue up 94%."
    assert a.source == "Basic" and a.category == "semis"
    assert a.published_at == datetime(2026, 11, 18, 10, 0, tzinfo=UTC)
    assert a.published_at.tzinfo is not None


def test_strip_title_suffix():
    arts = parse("google_news.xml", src("Reuters", strip_title_suffix=" - Reuters"))
    assert arts and not any(a.title.endswith(" - Reuters") for a in arts)
    assert arts[0].title == "TSMC raises capex to $42 billion"


def test_parse_youtube_atom():
    (a,) = parse("youtube.xml", src("Skill Up", category="gaming", kind="youtube"))
    assert a.title == "The State of AAA Gaming"
    assert a.url == "https://www.youtube.com/watch?v=abc"


def by_title(arts):
    return {a.title: a for a in arts}


def test_entry_without_date_skipped():
    assert "No date here" not in by_title(parse("bad_dates.xml"))


def test_naive_date_is_utc():
    assert by_title(parse("bad_dates.xml"))["Naive date"].published_at == datetime(2026, 11, 18, 9, 0, tzinfo=UTC)


def test_future_date_clamped():
    assert by_title(parse("bad_dates.xml"))["From the future"].published_at == NOW


def test_older_than_window_dropped():
    assert "Too old" not in by_title(parse("bad_dates.xml"))


def test_article_roundtrip():
    a = parse("rss_basic.xml")[0]
    d = a.to_dict()
    assert d["published_at"] == "2026-11-18T10:00:00Z"
    assert Article.from_dict(d) == a


def test_fetch_all_survives_failing_feed():
    a, b = src("A"), src("B")

    def http_get(url, timeout):
        if "a.test" in url:
            raise ConnectionError("boom")
        return (FIX / "rss_basic.xml").read_bytes()

    arts, errors = fetch_all([a, b], NOW, SETTINGS, http_get=http_get)
    assert len(arts) == 3 and all(x.source == "B" for x in arts)
    assert len(errors) == 1 and "A" in errors[0]


def test_fetch_all_dedupes_by_id():
    arts, errors = fetch_all([src("A"), src("B")], NOW, SETTINGS,
                             http_get=lambda u, t: (FIX / "rss_basic.xml").read_bytes())
    assert len(arts) == 3 and not errors
    assert [x.published_at for x in arts] == sorted((x.published_at for x in arts), reverse=True)
