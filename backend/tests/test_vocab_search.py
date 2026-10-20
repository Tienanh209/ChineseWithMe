"""M2 look-up. The "done when" cases from FEATURES.md come first."""

import pytest
from sqlalchemy import select

from app.models import VocabGroup, VocabGroupItem, Vocabulary, VocabularyTranslation

URL = "/api/vocab"


async def search(client, **params) -> dict:
    response = await client.get(URL, params={k: v for k, v in params.items() if v is not None})
    assert response.status_code == 200, response.text
    return response.json()


def words(result: dict) -> list[str]:
    return [item["traditional"] for item in result["items"]]


def keys(result: dict) -> list[tuple[str, str]]:
    return [(item["traditional"], item["pinyin"]) for item in result["items"]]


# the backlog's "done when" list ---------------------------------------------------------------


@pytest.mark.parametrize("query", ["nihao", "ni hao", "nǐ hǎo", "NI HAO", "Nǐhǎo", "  nǐ   hǎo "])
async def test_pinyin_with_or_without_tones_and_spaces_finds_nihao(client, seeded, query):
    result = await search(client, q=query)
    assert words(result)[0] == "你好"


async def test_nv_finds_nu(client, seeded):
    assert words(await search(client, q="nv")) == ["女"]
    assert words(await search(client, q="nü")) == ["女"]
    assert words(await search(client, q="nǚ")) == ["女"]


async def test_hanzi_prefix_finds_the_longer_word(client, seeded):
    assert words(await search(client, q="學")) == ["學", "學習"]  # exact first, then the word it starts


async def test_meaning_search_finds_words_in_any_language(client, seeded):
    en = await search(client, q="study")
    assert "學習" in words(en)
    vi = await search(client, q="học")
    assert words(vi)[:2] == ["學", "學習"]  # 學 means exactly "học"; 學習 is "học tập"
    assert "學習" in words(await search(client, q="HỌC TẬP"))  # case-insensitive, diacritics kept


async def test_both_readings_of_xing_are_separate_results(client, seeded):
    result = await search(client, q="行")
    assert ("行", "xíng") in keys(result) and ("行", "háng") in keys(result)
    assert len({item["id"] for item in result["items"]}) == len(result["items"])
    # ... and typing either reading finds only its own
    assert keys(await search(client, q="háng"))[0] == ("行", "háng")
    assert ("行", "xíng") not in keys(await search(client, q="háng"))


# ranking --------------------------------------------------------------------------------------


async def test_ranking_exact_reading_then_same_letters_then_prefix(db, client):
    for trad, pinyin in [("馬", "mǎ"), ("媽", "mā"), ("嗎", "ma"), ("螞蟻", "mǎyǐ"), ("麻煩", "máfán")]:
        db.add(Vocabulary(traditional=trad, simplified=trad, pinyin=pinyin, level="A1"))
    await db.flush()
    # mǎ: exactly that reading first; the same letters in other tones next; words that only start with it last
    assert words(await search(client, q="mǎ")) == ["馬", "媽", "嗎", "麻煩", "螞蟻"]
    # ma: the toneless entry is the exact reading here
    assert words(await search(client, q="ma")) == ["嗎", "馬", "媽", "麻煩", "螞蟻"]
    # tones are ignored for matching, not for ranking: the same results come back whichever tone is typed
    assert sorted(words(await search(client, q="mā"))) == sorted(words(await search(client, q="ma")))


async def test_meaning_ranking_exact_then_starts_then_word_inside(db, client):
    for trad, pinyin, meaning in [
        ("丙", "bǐng", "green tea"),
        ("乙", "yǐ", "tea leaves"),
        ("甲", "jiǎ", "tea"),
        ("丁", "dīng", "steam"),  # contains "tea" only inside a word: must not match
    ]:
        vocab = Vocabulary(traditional=trad, simplified=trad, pinyin=pinyin, level="A1")
        db.add(vocab)
        await db.flush()
        db.add(VocabularyTranslation(vocabulary_id=vocab.id, lang="en", meaning=meaning))
    await db.flush()
    assert words(await search(client, q="tea")) == ["甲", "乙", "丙"]  # exact, starts with, word inside


async def test_chinese_contains_ranks_after_exact_and_prefix(client, seeded):
    result = await search(client, q="行")
    assert words(result)[:2] == ["行", "行"]  # both exact readings
    assert words(result)[2:] == ["銀行"]  # contains, so after them
    assert words(await search(client, q="習")) == ["學習"]  # the character inside a longer word


async def test_simplified_characters_are_searched_too(client, seeded):
    assert words(await search(client, q="学习")) == ["學習"]
    assert words(await search(client, q="图书"))[0] == "圖書館"


async def test_zhuyin_search_ignores_spaces(client, seeded):
    assert words(await search(client, q="ㄋㄧˇㄏㄠˇ"))[0] == "你好"
    assert words(await search(client, q="ㄋㄧˇ ㄏㄠˇ"))[0] == "你好"
    assert "你" in words(await search(client, q="ㄋㄧˇ"))


# edge cases and safety ----------------------------------------------------------------------------


@pytest.mark.parametrize("query", ["%", "_", "\\", "%%", "_ _", "'", "' OR 1=1 --", '"; DROP TABLE vocabulary; --'])
async def test_wildcards_and_hostile_strings_are_literal(client, seeded, query):
    result = await search(client, q=query)
    assert result["total"] == 0 and result["items"] == []
    assert (await search(client))["total"] > 20  # and nothing was harmed


async def test_a_literal_percent_in_a_meaning_is_found_only_when_asked_for(db, client):
    vocab = Vocabulary(traditional="折", simplified="折", pinyin="zhé", level="A1")
    db.add(vocab)
    await db.flush()
    db.add(VocabularyTranslation(vocabulary_id=vocab.id, lang="en", meaning="20% off"))
    await db.flush()
    assert words(await search(client, q="20%")) == ["折"]
    assert words(await search(client, q="2%")) == []


async def test_single_letters_search_pinyin_only_not_meanings(client, seeded):
    # "n" starts the pinyin of exactly these seed words
    assert sorted(words(await search(client, q="n"))) == sorted(["你", "你好", "女"])
    # "d" and "e" would match English meanings (drink, every day, environment ...): with one
    # letter only pinyin is tried, and no seed pinyin starts with them
    assert words(await search(client, q="d")) == []
    assert words(await search(client, q="e")) == []
    # two letters do search meanings
    assert "喝" in words(await search(client, q="dr"))


async def test_word_start_not_substring_for_meanings(client, seeded):
    assert "學習" in words(await search(client, q="stud"))
    assert words(await search(client, q="tudy")) == []  # inside a word, not at its start


async def test_blank_or_punctuation_queries(client, seeded):
    browse = await search(client, q="   ")
    assert browse["total"] == (await search(client))["total"]
    assert (await search(client, q="'"))["items"] == []


async def test_query_length_is_limited(client):
    assert (await client.get(URL, params={"q": "a" * 101})).status_code == 422
    assert (await client.get(URL, params={"q": "a" * 100})).status_code == 200


async def test_mixed_script_query_is_treated_as_characters(client, seeded):
    assert words(await search(client, q="學x")) == []


# browsing, filters, pagination -------------------------------------------------------------------


async def test_browse_without_a_query_is_in_dictionary_order(client, seeded, db):
    result = await search(client, page_size=50)
    assert result["total"] == 25
    expected = list(await db.scalars(select(Vocabulary.id).order_by(Vocabulary.pinyin_normalized, Vocabulary.id)))
    assert [item["id"] for item in result["items"]] == expected
    assert keys(result)[:2] == [("行", "háng"), ("喝", "hē")]  # hang, he ...


async def test_level_filter(client, seeded):
    a1 = await search(client, level="A1")
    assert a1["total"] > 5 and {item["level"] for item in a1["items"]} == {"A1"}
    assert {item["level"] for item in (await search(client, level="C2"))["items"]} == {"C2"}
    assert words(await search(client, level="C2")) == ["一針見血"]
    assert words(await search(client, q="行", level="B1")) == ["行"]  # only the B1 reading
    assert (await client.get(URL, params={"level": "D1"})).status_code == 422


async def test_group_filter_uses_the_groups_own_order_when_browsing(client, seeded, db):
    group = await db.scalar(select(VocabGroup).where(VocabGroup.name == "Greetings and basics"))
    result = await search(client, group_id=group.id)
    assert words(result) == ["你好", "謝謝", "我", "你", "朋友"]  # the order the seed gave the group
    assert words(await search(client, group_id=group.id, q="ni")) == ["你", "你好"]  # ranked when searching
    assert words(await search(client, group_id=group.id, level="A2")) == []
    assert (await search(client, group_id=999_999))["total"] == 0


async def test_pagination(client, seeded):
    everything = await search(client, page_size=50)
    total = everything["total"]
    assert total >= 25 and len(everything["items"]) == total
    first = await search(client, page=1, page_size=10)
    second = await search(client, page=2, page_size=10)
    assert (first["page"], first["page_size"], first["total"]) == (1, 10, total)
    assert second["total"] == total
    assert [i["id"] for i in first["items"] + second["items"]] == [i["id"] for i in everything["items"][:20]]
    last_page = (total - 1) // 10 + 1
    assert len((await search(client, page=last_page, page_size=10))["items"]) == total - (last_page - 1) * 10
    beyond = await search(client, page=last_page + 1, page_size=10)
    assert beyond["items"] == [] and beyond["total"] == total  # the total survives an empty page


@pytest.mark.parametrize(
    "params", [{"page": 0}, {"page": -1}, {"page_size": 0}, {"page_size": 51}, {"group_id": 0}, {"page": "x"}]
)
async def test_pagination_bounds(client, params):
    assert (await client.get(URL, params=params)).status_code == 422


async def test_items_carry_everything_a_list_row_needs(client, seeded):
    item = (await search(client, q="你好"))["items"][0]
    assert item["traditional"] == "你好" and item["simplified"] == "你好" and item["pinyin"] == "nǐ hǎo"
    assert item["zhuyin"] == "ㄋㄧˇ ㄏㄠˇ" and item["level"] == "A1" and item["part_of_speech"] == "phrase"
    assert item["meanings"] == {"vi": ["xin chào"], "en": ["hello"]}
    assert item["audio_url"] is None and item["in_study_list"] is None  # anonymous


async def test_audio_path_becomes_a_url(db, client):
    db.add(Vocabulary(traditional="音", simplified="音", pinyin="yīn", level="A1", audio_path="vocabulary/yin.mp3"))
    await db.flush()
    assert (await search(client, q="音"))["items"][0]["audio_url"] == "/audio/vocabulary/yin.mp3"


async def test_in_study_list_flag_for_signed_in_users(user_client, db):
    ids = {i["traditional"]: i["id"] for i in (await search(user_client, q="ni"))["items"]}
    assert all(i["in_study_list"] is False for i in (await search(user_client, q="ni"))["items"])
    assert (await user_client.post(f"/api/study-list/{ids['你']}")).status_code == 200
    flags = {i["traditional"]: i["in_study_list"] for i in (await search(user_client, q="ni"))["items"]}
    assert flags == {"你": True, "你好": False}
    # another user's list is not shown
    await user_client.post("/api/auth/logout")
    user_client.cookies.clear()
    await user_client.post("/api/auth/login", json={"email": "admin@example.com", "password": "password123"})
    assert all(i["in_study_list"] is False for i in (await search(user_client, q="ni"))["items"])


async def test_search_is_rate_limited_per_ip(client, seeded):
    codes = [(await client.get(URL, params={"q": "ni"})).status_code for _ in range(121)]
    assert codes[:120] == [200] * 120 and codes[120] == 429


async def test_levels_and_groups_for_browsing(client, seeded):
    levels = (await client.get(f"{URL}/levels")).json()
    assert [row["level"] for row in levels] == ["A1", "A2", "B1", "B2", "C1", "C2"]
    assert {row["level"]: row["count"] for row in levels} == {"A1": 13, "A2": 6, "B1": 3, "B2": 1, "C1": 1, "C2": 1}

    groups = (await client.get(f"{URL}/groups")).json()
    assert [(g["name"], g["level"], g["count"]) for g in groups] == [
        ("Greetings and basics", "A1", 5),
        ("Daily life", "A2", 6),
    ]
    assert (await client.get(f"{URL}/groups", params={"level": "A2"})).json()[0]["name"] == "Daily life"
    assert (await client.get(f"{URL}/groups", params={"level": "C1"})).json() == []


async def test_levels_include_empty_levels(client):
    levels = (await client.get(f"{URL}/levels")).json()
    assert [row["count"] for row in levels] == [0] * 6


async def test_groups_without_a_level_come_last_and_empty_groups_count_zero(db, client):
    db.add_all([VocabGroup(name="No level"), VocabGroup(name="A one", level="A1")])
    await db.flush()
    assert [(g["name"], g["count"]) for g in (await client.get(f"{URL}/groups")).json()] == [
        ("A one", 0),
        ("No level", 0),
    ]


async def test_group_membership_is_not_duplicated_in_results(db, client):
    vocab = Vocabulary(traditional="好", simplified="好", pinyin="hǎo", level="A1")
    groups = [VocabGroup(name="G1"), VocabGroup(name="G2")]
    db.add(vocab)
    db.add_all(groups)
    await db.flush()
    db.add_all(VocabGroupItem(group_id=g.id, vocabulary_id=vocab.id) for g in groups)
    await db.flush()
    assert (await search(client, q="hǎo"))["total"] == 1  # two groups, one word
