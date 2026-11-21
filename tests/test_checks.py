from newsbot.checks import check_post, validate_picks
from newsbot.config import Settings

S = Settings("m", "medium", 15, 24, 30, 280, ["game-changer", "masterstroke"], 15)


def p(i):
    return {"article_id": f"id{i}", "post": "A real one-sentence post.", "reason": "r"}


def test_clean_post_has_no_flags():
    assert check_post("Nvidia made $35B last quarter. Somehow still not enough.", S) == []


def test_flags_too_long():
    assert "too_long" in check_post("a" * 281, S)
    assert check_post("a" * 280, S) == []


def test_flags_hashtag_and_link():
    flags = check_post("Big news #AI see https://x.com", S)
    assert "hashtag" in flags and "link" in flags
    assert "link" in check_post("read www.example.com", S)


def test_flags_hype_case_insensitive():
    assert check_post("A Game-Changer for chips", S) == ["hype:game-changer"]


def test_flags_empty():
    assert check_post("   ", S) == ["empty"]


def test_validate_picks_drops_unknown_ids():
    assert validate_picks([p(1), p(9)], {"id1", "id2"}, set(), 3) == [p(1)]


def test_validate_picks_drops_duplicates_and_already_picked():
    assert validate_picks([p(1), p(1), p(2), p(3)], {"id1", "id2", "id3"}, {"id2"}, 3) == [p(1), p(3)]


def test_validate_picks_truncates_to_max():
    ids = {f"id{i}" for i in range(5)}
    assert validate_picks([p(i) for i in range(5)], ids, set(), 3) == [p(0), p(1), p(2)]


def test_card_flags():
    from newsbot.checks import check_card
    assert check_card("$3.79B on day one") == []
    assert check_card("") == ["card_empty"]
    assert check_card("x" * 61) == ["card_too_long"]
    assert check_card("x" * 60) == []
    assert set(check_card("#AI www.x.com")) == {"card_hashtag", "card_link"}


def test_validate_picks_drops_placeholder_and_empty_posts():
    picks = [{"article_id": "id1", "post": "placeholder", "reason": "placeholder", "card_text": "placeholder"},
             {"article_id": "id2", "post": "  ", "reason": "r", "card_text": "c"},
             {"article_id": "id3", "post": "TBD", "reason": "r", "card_text": "c"},
             {"article_id": "id4", "post": "Nvidia made $35B. Still not enough, apparently.", "reason": "r", "card_text": "$35B"}]
    out = validate_picks(picks, {"id1", "id2", "id3", "id4"}, set(), 3)
    assert [p["article_id"] for p in out] == ["id4"]


def test_real_post_mentioning_tbd_survives():
    picks = [{"article_id": "id1", "post": "Launch date TBD, as usual.", "reason": "r", "card_text": "c"},
             {"article_id": "id2", "post": "A todo app raised $40M. Productivity remains elusive.", "reason": "r", "card_text": "c"}]
    assert len(validate_picks(picks, {"id1", "id2"}, set(), 3)) == 2


def test_placeholder_card_text_is_flagged():
    from newsbot.checks import check_card
    assert check_card("placeholder") == ["card_placeholder"]
    assert check_card("Price TBD") == []
