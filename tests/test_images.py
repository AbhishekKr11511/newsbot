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
    assert "license_type=commercial,modification" in get.calls[0]
    assert "extension=jpg,png" in get.calls[0]
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


# ---- ranker + find_images ----------------------------------------------------
import base64  # noqa: E402

from newsbot.config import ImageSettings  # noqa: E402
from newsbot.images import BadImage, RankError, find_images, ollama_ranker  # noqa: E402


class FakePostResp:
    def __init__(self, payload=None, exc=None):
        self.payload, self.exc = payload, exc

    def raise_for_status(self):
        if self.exc:
            raise self.exc

    def json(self):
        return self.payload


def fake_post(content=None, exc=None, record=None):
    def post(url, json=None, timeout=None):
        if record is not None:
            record.append((url, json, timeout))
        if isinstance(exc, requests.ConnectionError):
            raise exc
        return FakePostResp({"message": {"content": content}}, exc)
    return post


def test_ranker_parses_match():
    sent = []
    rank = ollama_ranker(ImageSettings(), post=fake_post('{"shows": "GTA cover art", "match": "yes", "usable": true}',
                                                         record=sent))
    assert rank(b"img", "GTA 6 is being review-bombed", "Grand Theft Auto VI") == 9
    url, body, timeout = sent[0]
    assert url == "http://localhost:11434/api/chat" and timeout == 60
    assert body["model"] == "gemma3:4b" and body["stream"] is False
    assert body["options"]["temperature"] == 0
    assert body["messages"][0]["images"] == [base64.b64encode(b"img").decode()]
    assert "Grand Theft Auto VI" in body["messages"][0]["content"]
    assert set(body["format"]["required"]) == {"shows", "match", "usable"}


def test_ranker_score_mapping():
    def score(match, usable):
        content = json.dumps({"shows": "x", "match": match, "usable": usable})
        return ollama_ranker(ImageSettings(), post=fake_post(content))(b"i", "p", "q")
    assert score("yes", True) == 9
    assert score("partly", True) == 6
    assert score("no", True) == 2
    assert score("yes", False) == 6
    assert score("no", False) == 0


def test_ranker_bad_json_raises():
    with pytest.raises(RankError):
        ollama_ranker(ImageSettings(), post=fake_post("nope"))(b"i", "p", "q")
    with pytest.raises(RankError):
        ollama_ranker(ImageSettings(), post=fake_post('{"shows": "x", "usable": true}'))(b"i", "p", "q")
    with pytest.raises(RankError):
        ollama_ranker(ImageSettings(), post=fake_post('{"shows": "x", "match": "maybe", "usable": true}'))(b"i", "p", "q")
    with pytest.raises(RankError):
        ollama_ranker(ImageSettings(), post=fake_post(exc=requests.ConnectionError("refused")))(b"i", "p", "q")
    with pytest.raises(RankError):
        ollama_ranker(ImageSettings(), post=fake_post(exc=requests.HTTPError("404 model not found")))(b"i", "p", "q")


def cand(source, name):
    url = f"https://img.test/{name}.jpg"
    return {"url": url, "thumb": url, "page_url": url, "source": source, "credit": name, "license": "L"}


def fake_sources(results, calls=None):
    """results: {(source, query): list | Exception}"""
    def make(source):
        def search(query, http_get, timeout):
            if calls is not None:
                calls.append((source, query))
            r = results.get((source, query), [])
            if isinstance(r, Exception):
                raise r
            return list(r)
        return search
    return {s: make(s) for s in ("wikimedia", "steam", "openverse")}


JPEG = b"\xff\xd8\xff"


def thumb_get(url, timeout):
    return JPEG + url.encode()


def scorer(scores, calls=None):
    """Ranker scoring by image name; records the order of calls."""
    def rank(img, post, query):
        name = img[len(JPEG):].decode().rsplit("/", 1)[1].removesuffix(".jpg")
        if calls is not None:
            calls.append(name)
        return scores[name]
    return rank


def pick(*searches, post="post"):
    return {"post": post, "image_searches": [{"source": s, "query": q} for s, q in searches]}


class Clock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


def names(p):
    return [i["credit"] for i in p["images"]]


def test_find_images_ranks_and_keeps_top():
    p = pick(("wikimedia", "q"))
    src = fake_sources({("wikimedia", "q"): [cand("wikimedia", n) for n in "abcd"]})
    find_images([p], ImageSettings(), 5, thumb_get=thumb_get, ranker=scorer({"a": 9, "b": 3, "c": 7, "d": 6}),
                sources=src)
    # one source only: the per-source cap gives way so empty slots are filled
    assert names(p) == ["a", "c", "d"]
    assert [i["score"] for i in p["images"]] == [9, 7, 6]


def test_scores_sorted_and_low_dropped_across_sources():
    p = pick(("wikimedia", "q"), ("openverse", "q"))
    src = fake_sources({("wikimedia", "q"): [cand("wikimedia", "a"), cand("wikimedia", "b")],
                        ("openverse", "q"): [cand("openverse", "c"), cand("openverse", "d")]})
    find_images([p], ImageSettings(), 5, thumb_get=thumb_get,
                ranker=scorer({"a": 9, "b": 3, "c": 7, "d": 6}), sources=src)
    assert names(p) == ["a", "c", "d"]


def test_max_two_per_source():
    p = pick(("steam", "g"), ("wikimedia", "w"))
    src = fake_sources({("steam", "g"): [cand("steam", f"s{i}") for i in range(5)],
                        ("wikimedia", "w"): [cand("wikimedia", "w1")]})
    scores = {f"s{i}": 9 for i in range(5)} | {"w1": 6}
    find_images([p], ImageSettings(), 5, thumb_get=thumb_get, ranker=scorer(scores), sources=src)
    # mix first (2 steam + the wikimedia), then fill the last slot with the next best steam
    assert [i["source"] for i in p["images"]] == ["steam", "steam", "wikimedia", "steam"]


def test_max_scored_round_robin():
    p = pick(("wikimedia", "1"), ("openverse", "2"))
    src = fake_sources({("wikimedia", "1"): [cand("wikimedia", f"1{c}") for c in "abcde"],
                        ("openverse", "2"): [cand("openverse", f"2{c}") for c in "abcde"]})
    calls = []
    find_images([p], ImageSettings(max_scored=4), 5, thumb_get=thumb_get,
                ranker=scorer({n: 5 for n in ["1a", "2a", "1b", "2b"]}, calls), sources=src)
    assert calls == ["1a", "2a", "1b", "2b"]


def test_ranker_down_gives_unranked_images():
    p1, p2 = pick(("wikimedia", "a")), pick(("steam", "b"))
    src = fake_sources({("wikimedia", "a"): [cand("wikimedia", n) for n in ("a1", "a2", "a3")],
                        ("steam", "b"): [cand("steam", n) for n in ("b1", "b2")]})
    calls = []

    def dead(img, post, query):
        calls.append(img)
        raise RankError("connection refused")

    find_images([p1, p2], ImageSettings(), 5, thumb_get=thumb_get, ranker=dead, sources=src)
    assert len(calls) == 1
    assert names(p1) == ["a1", "a2", "a3"] and names(p2) == ["b1", "b2"]
    assert all(i["score"] is None for i in p1["images"] + p2["images"])


def test_no_ranker_gives_unranked_images():
    p = pick(("wikimedia", "a"), ("openverse", "b"))
    src = fake_sources({("wikimedia", "a"): [cand("wikimedia", n) for n in ("a1", "a2", "a3")],
                        ("openverse", "b"): [cand("openverse", n) for n in ("b1", "b2", "b3")]})
    find_images([p], ImageSettings(), 5, thumb_get=thumb_get, ranker=None, sources=src)
    assert names(p) == ["a1", "b1", "a2", "b2"]


def test_budget_exhausted_in_phase1():
    clock = Clock()
    p1, p2 = pick(("wikimedia", "a")), pick(("steam", "b"))
    calls = []
    base = fake_sources({("wikimedia", "a"): [cand("wikimedia", "a1")], ("steam", "b"): [cand("steam", "b1")]}, calls)

    def slow_wikimedia(q, g, t):
        clock.t += 1000
        return base["wikimedia"](q, g, t)

    src = {**base, "wikimedia": slow_wikimedia}
    rank_calls = []
    find_images([p1, p2], ImageSettings(budget_s=300), 5, thumb_get=thumb_get,
                ranker=scorer({"a1": 9, "b1": 9}, rank_calls), clock=clock, sources=src)
    assert names(p1) == ["a1"] and p1["images"][0]["score"] is None
    assert p2["images"] == []
    assert ("steam", "b") not in calls and rank_calls == []


def test_rank_round_robin_across_picks():
    clock = Clock()
    p1, p2 = pick(("wikimedia", "a")), pick(("steam", "b"))
    src = fake_sources({("wikimedia", "a"): [cand("wikimedia", n) for n in ("a1", "a2")],
                        ("steam", "b"): [cand("steam", n) for n in ("b1", "b2")]})
    calls = []
    inner = scorer({"a1": 9, "a2": 8, "b1": 7, "b2": 6}, calls)

    def ranker(img, post, query):
        clock.t += 100
        return inner(img, post, query)

    find_images([p1, p2], ImageSettings(budget_s=200), 5, thumb_get=thumb_get, ranker=ranker, clock=clock,
                sources=src)
    assert calls == ["a1", "b1"]
    assert [(i["credit"], i["score"]) for i in p1["images"]] == [("a1", 9), ("a2", None)]
    assert [(i["credit"], i["score"]) for i in p2["images"]] == [("b1", 7), ("b2", None)]


def test_disabled_source_skipped():
    calls = []
    src = fake_sources({("openverse", "x"): SourceUnavailable("429"), ("openverse", "y"): [cand("openverse", "o")],
                        ("wikimedia", "w"): [cand("wikimedia", "w1")]}, calls)
    p1, p2 = pick(("openverse", "x")), pick(("openverse", "y"), ("wikimedia", "w"))
    find_images([p1, p2], ImageSettings(), 5, thumb_get=thumb_get, ranker=None, sources=src)
    assert ("openverse", "y") not in calls
    assert names(p2) == ["w1"]


def test_search_exception_isolated():
    src = fake_sources({("steam", "x"): ValueError("bad json"), ("wikimedia", "w"): [cand("wikimedia", "w1")]})
    p = pick(("steam", "x"), ("wikimedia", "w"))
    find_images([p], ImageSettings(), 5, thumb_get=thumb_get, ranker=None, sources=src)
    assert names(p) == ["w1"]


def test_source_not_enabled_is_skipped():
    calls = []
    src = fake_sources({("steam", "x"): [cand("steam", "s")]}, calls)
    p = pick(("steam", "x"))
    find_images([p], ImageSettings(sources=["wikimedia"]), 5, thumb_get=thumb_get, ranker=None, sources=src)
    assert calls == [] and p["images"] == []


def test_thumb_download_failure_drops_candidate():
    src = fake_sources({("wikimedia", "q"): [cand("wikimedia", "a"), cand("wikimedia", "b")]})

    def get(url, timeout):
        if url.endswith("a.jpg"):
            raise TimeoutError("slow")
        return JPEG + url.encode()

    p = pick(("wikimedia", "q"))
    find_images([p], ImageSettings(), 5, thumb_get=get, ranker=scorer({"b": 8}), sources=src)
    assert names(p) == ["b"]


def test_duplicate_urls_removed():
    src = fake_sources({("wikimedia", "1"): [cand("wikimedia", "a")], ("wikimedia", "2"): [cand("wikimedia", "a"),
                                                                                        cand("wikimedia", "b")]})
    p = pick(("wikimedia", "1"), ("wikimedia", "2"))
    find_images([p], ImageSettings(), 5, thumb_get=thumb_get, ranker=None, sources=src)
    assert names(p) == ["a", "b"]


def test_pick_without_searches_gets_empty_images():
    p = {"post": "x"}
    find_images([p], ImageSettings(), 5, thumb_get=thumb_get, ranker=None, sources=fake_sources({}))
    assert p["images"] == []


def test_ranker_gets_the_search_query():
    seen = []
    src = fake_sources({("steam", "Halo Infinite"): [cand("steam", "h")]})
    p = pick(("steam", "Halo Infinite"), post="Halo news")
    find_images([p], ImageSettings(), 5, thumb_get=thumb_get,
                ranker=lambda img, post, query: seen.append((post, query)) or 9, sources=src)
    assert seen == [("Halo news", "Halo Infinite")]


# ---- thumbnail downloads only reach public hosts -------------------------------
from newsbot import images as images_mod  # noqa: E402


class Resp:
    def __init__(self, status=200, headers=None, body=b"img"):
        self.status_code, self.headers, self.body = status, headers or {}, body
        self.is_redirect = status in (301, 302, 303, 307, 308) and "Location" in self.headers

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(response=self)

    def iter_content(self, chunk_size):
        yield self.body

    def close(self):
        pass


def fake_dns(monkeypatch, table):
    def getaddrinfo(host, *a, **k):
        if host not in table:
            raise OSError("no such host")
        return [(2, 1, 6, "", (table[host], 0))]
    monkeypatch.setattr(images_mod.socket, "getaddrinfo", getaddrinfo)


@pytest.mark.parametrize("url", ["http://127.0.0.1/x.jpg", "http://192.168.1.1/x.jpg", "http://10.0.0.5/x.jpg",
                                 "http://169.254.169.254/latest", "http://localhost/x.jpg", "http://[::1]/x.jpg",
                                 "http://router.lan/x.jpg"])
def test_public_get_refuses_private_hosts(monkeypatch, url):
    fake_dns(monkeypatch, {"localhost": "127.0.0.1", "router.lan": "192.168.0.1", "127.0.0.1": "127.0.0.1",
                           "192.168.1.1": "192.168.1.1", "10.0.0.5": "10.0.0.5", "169.254.169.254": "169.254.169.254",
                           "::1": "::1"})
    called = []
    monkeypatch.setattr(images_mod.requests, "get", lambda *a, **k: called.append(a) or Resp())
    with pytest.raises(ValueError):
        images_mod.public_get(url, 5)
    assert called == []


def test_public_get_checks_redirect_targets(monkeypatch):
    fake_dns(monkeypatch, {"img.test": "93.184.216.34", "10.1.1.1": "10.1.1.1"})
    calls = []

    def get(url, **k):
        calls.append((url, k.get("allow_redirects")))
        return Resp(302, {"Location": "http://10.1.1.1/admin"})

    monkeypatch.setattr(images_mod.requests, "get", get)
    with pytest.raises(ValueError):
        images_mod.public_get("https://img.test/a.jpg", 5)
    assert calls == [("https://img.test/a.jpg", False)]


def test_public_get_follows_public_redirect(monkeypatch):
    fake_dns(monkeypatch, {"img.test": "93.184.216.34", "cdn.test": "151.101.1.1"})
    replies = iter([Resp(301, {"Location": "https://cdn.test/a.jpg"}), Resp(200, body=b"pixels")])
    monkeypatch.setattr(images_mod.requests, "get", lambda url, **k: next(replies))
    assert images_mod.public_get("https://img.test/a.jpg", 5) == b"pixels"


def test_public_get_too_many_redirects(monkeypatch):
    fake_dns(monkeypatch, {"img.test": "93.184.216.34"})
    monkeypatch.setattr(images_mod.requests, "get", lambda url, **k: Resp(302, {"Location": "https://img.test/again"}))
    with pytest.raises(ValueError):
        images_mod.public_get("https://img.test/a.jpg", 5)


def test_find_images_default_thumb_get_is_public_get():
    import inspect
    assert inspect.signature(find_images).parameters["thumb_get"].default is images_mod.public_get


def test_steam_requires_name_match():
    search = json.dumps({"total": 2, "items": [{"type": "app", "name": "Grand Theft Auto V Enhanced", "id": 1},
                                               {"type": "app", "name": "Grand Theft Auto VI", "id": 3240220}]}).encode()
    get = Router({"storesearch": search, "appdetails": fixture_bytes("steam_appdetails.json")})
    out = search_steam("Grand Theft Auto VI", get, 5)
    assert "appids=3240220" in get.calls[1] and len(out) == 3


def test_steam_no_name_match_empty():
    search = json.dumps({"total": 1, "items": [{"type": "app", "name": "Grand Theft Auto V Enhanced", "id": 1}]}).encode()
    get = Router({"storesearch": search})
    assert search_steam("Grand Theft Auto VI", get, 5) == []
    assert len(get.calls) == 1


def test_steam_name_match_ignores_case_and_punctuation():
    search = json.dumps({"total": 1, "items": [{"type": "app", "name": "Call of Duty®: Black Ops 7", "id": 3240220}]}).encode()
    get = Router({"storesearch": search, "appdetails": fixture_bytes("steam_appdetails.json")})
    assert len(search_steam("call of duty black ops 7", get, 5)) == 3


def test_ranker_http_400_is_bad_image():
    resp = requests.Response()
    resp.status_code = 400
    with pytest.raises(BadImage):
        ollama_ranker(ImageSettings(), post=fake_post(exc=requests.HTTPError(response=resp)))(b"i", "p", "q")
    assert issubclass(BadImage, RankError)


def test_bad_image_does_not_stop_ranking():
    src = fake_sources({("wikimedia", "q"): [cand("wikimedia", n) for n in ("a", "b")],
                        ("steam", "s"): [cand("steam", "c")]})
    calls = []

    def ranker(img, post, query):
        name = img[len(JPEG):].decode().rsplit("/", 1)[1].removesuffix(".jpg")
        calls.append(name)
        if name == "a":
            raise BadImage("Failed to load image")
        return 9

    p = pick(("wikimedia", "q"), ("steam", "s"))
    find_images([p], ImageSettings(), 5, thumb_get=thumb_get, ranker=ranker, sources=src)
    assert calls == ["a", "c", "b"]
    assert names(p) == ["c", "b"] and all(i["score"] == 9 for i in p["images"])


def test_non_raster_thumb_is_dropped_without_ranking():
    src = fake_sources({("openverse", "q"): [cand("openverse", "svg"), cand("openverse", "ok")]})
    calls = []

    def get(url, timeout):
        return b"<?xml version='1.0'?><svg/>" if "svg" in url else JPEG + url.encode()

    p = pick(("openverse", "q"))
    find_images([p], ImageSettings(), 5, thumb_get=get, ranker=scorer({"ok": 9}, calls), sources=src)
    assert calls == ["ok"] and names(p) == ["ok"]


def test_ollama_rejecting_every_image_falls_back_to_unranked():
    # e.g. a non-vision model configured: Ollama answers 400 for every request
    src = fake_sources({("wikimedia", "q"): [cand("wikimedia", n) for n in ("a", "b", "c", "d")],
                        ("steam", "s"): [cand("steam", n) for n in ("e", "f")]})
    calls = []

    def ranker(img, post, query):
        calls.append(1)
        raise BadImage("model does not support images")

    p1, p2 = pick(("wikimedia", "q")), pick(("steam", "s"))
    find_images([p1, p2], ImageSettings(), 5, thumb_get=thumb_get, ranker=ranker, sources=src)
    assert len(calls) == 3
    assert names(p1) == ["a", "b", "c", "d"] and names(p2) == ["e", "f"]
    assert all(i["score"] is None for i in p1["images"] + p2["images"])


def test_bad_image_streak_resets_after_a_success():
    src = fake_sources({("wikimedia", "q"): [cand("wikimedia", n) for n in ("a", "b", "c", "d", "e")]})
    seq = iter(["bad", "bad", 9, "bad", "bad"])

    def ranker(img, post, query):
        r = next(seq)
        if r == "bad":
            raise BadImage("x")
        return r

    p = pick(("wikimedia", "q"))
    find_images([p], ImageSettings(), 5, thumb_get=thumb_get, ranker=ranker, sources=src)
    assert names(p) == ["c"] and p["images"][0]["score"] == 9


# ---- regression: deferred review minors -----------------------------------------

def test_steam_query_without_latin_words_matches_nothing():  # M3
    get = Router({"storesearch": fixture_bytes("steam_search.json")})
    assert search_steam("東方", get, 5) == []
    assert search_steam("!!!", get, 5) == []


def test_ranker_caps_generation_length():  # M4
    sent = []
    ollama_ranker(ImageSettings(), post=fake_post('{"shows": "x", "match": "yes", "usable": true}', record=sent))(
        b"i", "p", "q")
    assert sent[0][1]["options"]["num_predict"] == 128


def test_openverse_credit_is_plain_text():  # M6
    data = json.dumps({"results": [{"title": "Rock &amp; <b>Roll</b>", "creator": "<i>Ann</i>", "source": "flickr",
                                    "url": "https://live.staticflickr.com/1.jpg", "license": "by",
                                    "license_version": "2.0", "foreign_landing_url": "https://flickr.com/p/1"}]})
    out = search_openverse("x", Router({"openverse": data.encode()}), 5)
    assert out[0]["credit"] == "Rock & Roll by Ann (flickr)"
