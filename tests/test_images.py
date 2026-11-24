from newsbot.images import clean_searches, screenshot_link


def test_clean_searches():
    raw = [{"source": "steam", "query": " GTA 6 "}, {"source": "pexels", "query": "x"},
           {"source": "wikimedia", "query": ""}, {"source": "wikimedia", "query": "a" * 81},
           {"source": "openverse", "query": "server room"}, {"source": "wikimedia", "query": "Satya Nadella"},
           {"source": "steam", "query": "Halo"}]
    assert clean_searches(raw) == [{"source": "steam", "query": "GTA 6"},
                                   {"source": "openverse", "query": "server room"},
                                   {"source": "wikimedia", "query": "Satya Nadella"}]
    assert clean_searches(None) == []
    assert clean_searches([{"source": "steam"}, "junk"]) == []


def test_screenshot_link():
    assert screenshot_link({"text": "Metacritic user score for GTA 6", "search": "GTA 6 metacritic user score"}) == {
        "text": "Metacritic user score for GTA 6",
        "url": "https://www.google.com/search?q=GTA+6+metacritic+user+score"}
    assert screenshot_link({"text": "", "search": "x"}) is None
    assert screenshot_link({"text": "x", "search": "  "}) is None
    assert screenshot_link(None) is None


# ---- sources -------------------------------------------------------------
import json  # noqa: E402
from pathlib import Path  # noqa: E402

import pytest  # noqa: E402
import requests  # noqa: E402

from newsbot.images import SOURCES, SourceUnavailable, search_openverse, search_steam, search_wikimedia  # noqa: E402

FIX = Path(__file__).parent / "fixtures"


def fixture_bytes(name):
    return (FIX / name).read_bytes()


class Router:
    """Fake http_get: returns fixture bytes chosen by a substring of the URL; records calls."""

    def __init__(self, routes):
        self.routes, self.calls = routes, []

    def __call__(self, url, timeout):
        self.calls.append(url)
        for key, value in self.routes.items():
            if key in url:
                if isinstance(value, Exception):
                    raise value
                return value
        raise AssertionError(f"unexpected url {url}")


def test_sources_registry():
    assert set(SOURCES) == {"wikimedia", "steam", "openverse"}


def test_wikimedia_parses():
    get = Router({"commons.wikimedia.org": fixture_bytes("wikimedia.json")})
    out = search_wikimedia("Satya Nadella", get, 5)
    assert "gsrsearch=Satya%20Nadella%20filetype%3Abitmap" in get.calls[0] or "Satya%20Nadella" in get.calls[0]
    assert len(out) == 3
    first = out[0]
    assert first["source"] == "wikimedia"
    assert first["url"].startswith("https://upload.wikimedia.org/")
    assert first["thumb"].startswith("https://")
    assert first["page_url"].startswith("https://commons.wikimedia.org/")
    assert first["credit"] == "Brian Smale and Microsoft"
    assert first["license"] == "CC BY-SA 4.0"


def test_wikimedia_credit_strips_html():
    out = search_wikimedia("x", Router({"commons": fixture_bytes("wikimedia.json")}), 5)
    credit = out[2]["credit"]
    assert credit == "Jane Doe"
    assert "<" not in credit and "script" not in credit


def test_steam_two_calls_max_three():
    get = Router({"storesearch": fixture_bytes("steam_search.json"), "appdetails": fixture_bytes("steam_appdetails.json")})
    out = search_steam("Grand Theft Auto V", get, 5)
    assert len(get.calls) == 2 and "appids=3240220" in get.calls[1]
    assert len(out) == 3
    assert "header.jpg" in out[0]["url"] and out[0]["thumb"] == out[0]["url"]
    assert "1920x1080" in out[1]["url"] and "600x338" in out[1]["thumb"]
    assert out[0]["page_url"] == "https://store.steampowered.com/app/3240220/"
    assert out[0]["credit"] == "Official art · Steam" and out[0]["license"] == "Promotional"


def test_steam_no_match_empty():
    get = Router({"storesearch": b'{"total": 0, "items": []}'})
    assert search_steam("Nope", get, 5) == []
    assert len(get.calls) == 1


def test_openverse_parses_and_drops_unsafe():
    get = Router({"api.openverse.org/v1/images/?": fixture_bytes("openverse.json")})
    out = search_openverse("server room", get, 5)
    assert "license_type=commercial,modification" in get.calls[0] or "license_type=commercial%2Cmodification" in get.calls[0]
    titles = [c["credit"] for c in out]
    assert len(out) == 3 and not any(c["credit"].startswith("Bad") for c in out)
    assert out[0]["license"] == "CC BY-SA 2.0"
    assert out[0]["credit"] == "17° Server Room @ Work by Leonardo Rizzi (flickr)"
    assert out[0]["page_url"].startswith("https://www.flickr.com/")
    assert out[2]["license"] == "CC0", titles


def test_openverse_429_disables_source():
    resp = requests.Response()
    resp.status_code = 429
    get = Router({"openverse": requests.HTTPError(response=resp)})
    with pytest.raises(SourceUnavailable):
        search_openverse("x", get, 5)


def test_other_http_errors_propagate():
    resp = requests.Response()
    resp.status_code = 500
    with pytest.raises(requests.HTTPError):
        search_wikimedia("x", Router({"commons": requests.HTTPError(response=resp)}), 5)
