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
