from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update

from app.models import UserVocabProgress, Vocabulary, VocabularyExample, VocabularyTranslation
from app.security import CSRF_HEADER


async def word_id(db, traditional, pinyin) -> int:
    return await db.scalar(
        select(Vocabulary.id).where(Vocabulary.traditional == traditional, Vocabulary.pinyin == pinyin)
    )


# detail ------------------------------------------------------------------------------------------


async def test_detail_has_readings_meanings_examples_and_groups(client, seeded, db):
    vocab_id = await word_id(db, "學習", "xuéxí")
    response = await client.get(f"/api/vocab/{vocab_id}", params={"lang": "en"})
    assert response.status_code == 200
    body = response.json()
    assert (body["traditional"], body["simplified"], body["pinyin"], body["zhuyin"]) == (
        "學習",
        "学习",
        "xuéxí",
        "ㄒㄩㄝˊ ㄒㄧˊ",
    )
    assert (body["part_of_speech"], body["level"]) == ("verb", "A2")
    assert body["translations"] == [
        {"lang": "en", "meanings": ["to study, to learn"]},
        {"lang": "vi", "meanings": ["học tập"]},
    ]
    assert [e["hanzi"] for e in body["examples"]] == ["我每天學習中文。"]
    assert body["examples"][0]["translations"]["vi"] == "Mỗi ngày tôi học tiếng Trung."
    assert body["examples"][0]["audio_url"] is None
    assert body["groups"] == []
    assert body["study"] is None


async def test_translations_list_the_requested_language_first(client, seeded, db):
    vocab_id = await word_id(db, "你好", "nǐ hǎo")

    async def order(**params):
        body = (await client.get(f"/api/vocab/{vocab_id}", params=params)).json()
        return [t["lang"] for t in body["translations"]]

    assert await order(lang="en") == ["en", "vi"]
    assert await order(lang="vi") == ["vi", "en"]
    assert await order() == ["vi", "en"]  # default
    assert await order(lang="fr") == ["en", "vi"]  # not available: the rest in alphabetical order


async def test_signed_in_users_language_is_the_default(user_client, db):
    vocab_id = await word_id(db, "你好", "nǐ hǎo")
    await user_client.patch("/api/me", json={"ui_lang": "en"})
    body = (await user_client.get(f"/api/vocab/{vocab_id}")).json()
    assert [t["lang"] for t in body["translations"]] == ["en", "vi"]
    explicit = (await user_client.get(f"/api/vocab/{vocab_id}", params={"lang": "vi"})).json()
    assert [t["lang"] for t in explicit["translations"]] == ["vi", "en"]  # the parameter wins


async def test_meanings_keep_their_sort_order(db, client):
    vocab = Vocabulary(traditional="多", simplified="多", pinyin="duō", level="A1")
    db.add(vocab)
    await db.flush()
    db.add_all(
        VocabularyTranslation(vocabulary_id=vocab.id, lang="en", meaning=m, sort_order=i)
        for i, m in enumerate(["many", "much", "more"])
    )
    await db.flush()
    body = (await client.get(f"/api/vocab/{vocab.id}", params={"lang": "en"})).json()
    assert body["translations"] == [{"lang": "en", "meanings": ["many", "much", "more"]}]


async def test_both_readings_of_a_polyphone_are_listed_with_the_current_one_marked(client, seeded, db):
    xing, hang = await word_id(db, "行", "xíng"), await word_id(db, "行", "háng")
    body = (await client.get(f"/api/vocab/{xing}", params={"lang": "en"})).json()
    readings = {r["pinyin"]: r for r in body["readings"]}
    assert set(readings) == {"xíng", "háng"}
    assert (readings["xíng"]["id"], readings["xíng"]["current"]) == (xing, True)
    assert (readings["háng"]["id"], readings["háng"]["current"]) == (hang, False)
    assert readings["háng"]["level"] == "B1" and readings["háng"]["zhuyin"] == "ㄏㄤˊ"
    assert readings["háng"]["meaning"] == "row; line of business"
    # from the other entry the marking flips
    other = (await client.get(f"/api/vocab/{hang}")).json()
    assert {r["pinyin"]: r["current"] for r in other["readings"]} == {"xíng": False, "háng": True}


async def test_a_word_with_one_reading_lists_only_itself(client, seeded, db):
    body = (await client.get(f"/api/vocab/{await word_id(db, '女', 'nǚ')}")).json()
    assert [(r["pinyin"], r["current"]) for r in body["readings"]] == [("nǚ", True)]


async def test_reading_meaning_follows_the_requested_language(client, seeded, db):
    xing = await word_id(db, "行", "xíng")
    vi = (await client.get(f"/api/vocab/{xing}", params={"lang": "vi"})).json()
    assert {r["pinyin"]: r["meaning"] for r in vi["readings"]}["háng"] == "hàng, dòng; ngành"


async def test_examples_are_ordered_and_audio_paths_become_urls(db, client):
    vocab = Vocabulary(traditional="音", simplified="音", pinyin="yīn", level="A1", audio_path="vocabulary/yin.mp3")
    db.add(vocab)
    await db.flush()
    db.add_all(
        [
            VocabularyExample(vocabulary_id=vocab.id, hanzi_text="第二句。", sort_order=2),
            VocabularyExample(
                vocabulary_id=vocab.id, hanzi_text="第一句。", sort_order=1, audio_path="vocabulary/examples/1 a.mp3"
            ),
        ]
    )
    await db.flush()
    body = (await client.get(f"/api/vocab/{vocab.id}")).json()
    assert body["audio_url"] == "/audio/vocabulary/yin.mp3"
    assert [e["hanzi"] for e in body["examples"]] == ["第一句。", "第二句。"]
    assert body["examples"][0]["audio_url"] == "/audio/vocabulary/examples/1%20a.mp3"  # path escaped
    assert body["examples"][1]["audio_url"] is None


async def test_groups_of_a_word(client, seeded, db):
    body = (await client.get(f"/api/vocab/{await word_id(db, '你好', 'nǐ hǎo')}")).json()
    assert [(g["name"], g["level"]) for g in body["groups"]] == [("Greetings and basics", "A1")]


async def test_unknown_and_malformed_ids(client, seeded):
    missing = await client.get("/api/vocab/999999")
    assert missing.status_code == 404 and missing.json()["error"]["code"] == "not_found"
    for bad in ("0", "-1", "abc", str(2**63)):
        assert (await client.get(f"/api/vocab/{bad}")).status_code == 422, bad
    assert (await client.get("/api/vocab/1", params={"lang": "english"})).status_code == 422


async def test_levels_and_groups_are_not_mistaken_for_ids(client):
    assert (await client.get("/api/vocab/levels")).status_code == 200
    assert (await client.get("/api/vocab/groups")).status_code == 200


# the study list -----------------------------------------------------------------------------------


async def test_adding_requires_sign_in(client, seeded, db):
    response = await client.post(f"/api/study-list/{await word_id(db, '女', 'nǚ')}")
    assert response.status_code == 401 and response.json()["error"]["code"] == "not_authenticated"
    assert (await db.scalar(select(UserVocabProgress.user_id).limit(1))) is None


async def test_add_creates_a_new_card_due_now(user_client, db):
    vocab_id = await word_id(db, "女", "nǚ")
    before = datetime.now(UTC)
    response = await user_client.post(f"/api/study-list/{vocab_id}")
    assert response.status_code == 200
    body = response.json()
    assert body["added"] is True and body["status"] == "new"
    assert (
        before - timedelta(minutes=1)
        <= datetime.fromisoformat(body["next_review_at"])
        <= datetime.now(UTC) + timedelta(minutes=1)
    )

    row = await db.scalar(select(UserVocabProgress).where(UserVocabProgress.vocabulary_id == vocab_id))
    assert (row.status, row.repetitions, row.interval_days, row.lapses, float(row.ease_factor)) == ("new", 0, 0, 0, 2.5)
    assert row.last_reviewed_at is None
    assert row.next_review_at <= datetime.now(UTC)  # due now, so the first flashcard session can pick it up


async def test_adding_twice_never_resets_progress(user_client, db):
    vocab_id = await word_id(db, "女", "nǚ")
    await user_client.post(f"/api/study-list/{vocab_id}")
    later = datetime.now(UTC) + timedelta(days=6)
    await db.execute(
        update(UserVocabProgress)
        .where(UserVocabProgress.vocabulary_id == vocab_id)
        .values(status="review", repetitions=3, interval_days=6, ease_factor=2.1, next_review_at=later)
    )
    again = await user_client.post(f"/api/study-list/{vocab_id}")
    assert again.status_code == 200
    body = again.json()
    assert body["added"] is False and body["status"] == "review"
    assert datetime.fromisoformat(body["next_review_at"]) == later
    row = await db.scalar(
        select(UserVocabProgress)
        .where(UserVocabProgress.vocabulary_id == vocab_id)
        .execution_options(populate_existing=True)
    )
    assert (row.repetitions, row.interval_days, round(row.ease_factor, 1)) == (3, 6, 2.1)


async def test_each_user_has_their_own_list(user_client, db):
    vocab_id = await word_id(db, "女", "nǚ")
    await user_client.post(f"/api/study-list/{vocab_id}")
    await user_client.post("/api/auth/logout")
    user_client.cookies.clear()
    await user_client.post("/api/auth/login", json={"email": "admin@example.com", "password": "password123"})
    user_client.headers[CSRF_HEADER] = user_client.cookies["csrf_token"]
    assert (await user_client.get(f"/api/vocab/{vocab_id}")).json()["study"] is None
    assert (await user_client.post(f"/api/study-list/{vocab_id}")).json()["added"] is True  # not "already there"


async def test_detail_shows_the_study_state(user_client, db):
    vocab_id = await word_id(db, "女", "nǚ")
    assert (await user_client.get(f"/api/vocab/{vocab_id}")).json()["study"] is None
    await user_client.post(f"/api/study-list/{vocab_id}")
    study = (await user_client.get(f"/api/vocab/{vocab_id}")).json()["study"]
    assert study["status"] == "new" and "next_review_at" in study


async def test_unknown_word_is_404_and_ids_are_validated(user_client):
    assert (await user_client.post("/api/study-list/999999")).status_code == 404
    for bad in ("0", "abc", str(2**63)):
        assert (await user_client.post(f"/api/study-list/{bad}")).status_code == 422, bad


async def test_adding_needs_the_csrf_header(user_client, db):
    vocab_id = await word_id(db, "女", "nǚ")
    del user_client.headers[CSRF_HEADER]
    response = await user_client.post(f"/api/study-list/{vocab_id}")
    assert response.status_code == 403 and response.json()["error"]["code"] == "csrf_failed"
    assert await db.scalar(select(UserVocabProgress.user_id).limit(1)) is None


async def test_deleting_a_word_removes_it_from_study_lists(user_client, db):
    vocab_id = await word_id(db, "女", "nǚ")
    await user_client.post(f"/api/study-list/{vocab_id}")
    await db.execute(Vocabulary.__table__.delete().where(Vocabulary.id == vocab_id))
    assert await db.scalar(select(UserVocabProgress.user_id).limit(1)) is None  # ON DELETE CASCADE
