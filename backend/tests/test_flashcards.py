"""M3 flashcards: sessions, answers, the daily cap, "today" in the user's time zone, streaks."""

import asyncio
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.deps import get_now
from app.errors import AppError
from app.main import app
from app.models import (
    User,
    UserVocabProgress,
    VocabGroup,
    VocabGroupItem,
    VocabReviewLog,
    Vocabulary,
    VocabularyExample,
    VocabularyTranslation,
)
from app.services import flashcards, srs
from app.services.flashcards import streak

VN = ZoneInfo("Asia/Ho_Chi_Minh")
NOW = datetime(2026, 10, 21, 3, 0, tzinfo=UTC)  # 10:00 on the 21st in Vietnam
SESSION, REVIEW, STATS = "/api/flashcards/session", "/api/flashcards/review", "/api/flashcards/stats"


def fix_clock(now: datetime = NOW) -> None:
    app.dependency_overrides[get_now] = lambda: now


async def me(db) -> User:
    return await db.scalar(
        select(User).where(User.email == "test@example.com").execution_options(populate_existing=True)
    )


async def make_words(db, count: int, *, level: str = "A1", start: int = 0) -> list[Vocabulary]:
    words = [
        Vocabulary(traditional=f"測{chr(0x4E00 + start + i)}", simplified="x", pinyin=f"cè{i + start}", level=level)
        for i in range(count)
    ]
    db.add_all(words)
    await db.flush()
    db.add_all(
        VocabularyTranslation(vocabulary_id=w.id, lang="en", meaning=f"meaning {w.id}", sort_order=0) for w in words
    )
    await db.flush()
    return words


async def add_card(
    db, user: User, vocab: Vocabulary, *, status="new", due=NOW, interval=0, reps=0, lapses=0, ease=2.5, added=None
):
    """A progress row in a state the database accepts: new <=> never reviewed."""
    reviewed = None if status == "new" else due - timedelta(days=max(interval, 1))
    progress = UserVocabProgress(
        user_id=user.id,
        vocabulary_id=vocab.id,
        status=status,
        ease_factor=ease,
        interval_days=interval,
        repetitions=reps,
        lapses=lapses,
        next_review_at=added or due,
        last_reviewed_at=reviewed,
        first_reviewed_at=reviewed,
    )
    db.add(progress)
    await db.flush()
    return progress


async def get_session(client, **params) -> dict:
    response = await client.get(SESSION, params=params)
    assert response.status_code == 200, response.text
    return response.json()


def ids(session: dict) -> list[int]:
    return [card["vocabulary_id"] for card in session["cards"]]


async def answer(client, vocab, rating):
    return await client.post(REVIEW, json={"vocabulary_id": vocab.id, "rating": rating})


# ---------------------------------------------------------------------------------------------------------
# the session
# ---------------------------------------------------------------------------------------------------------


async def test_requires_sign_in(client, seeded):
    for method, url in (("GET", SESSION), ("GET", STATS)):
        response = await client.request(method, url)
        assert response.status_code == 401 and response.json()["error"]["code"] == "not_authenticated"
    response = await client.post(REVIEW, json={"vocabulary_id": 1, "rating": 3})
    assert response.status_code == 401


async def test_an_empty_study_list_gives_an_empty_session(user_client):
    fix_clock()
    body = await get_session(user_client)
    assert body == {
        "cards": [],
        "due_total": 0,
        "new_waiting": 0,
        "new_allowance": 20,
        "new_today": 0,
        "daily_new_cards": 20,
    }


async def test_due_reviews_come_first_most_overdue_first_then_new_cards(user_client, db):
    fix_clock()
    user = await me(db)
    w = await make_words(db, 6)
    await add_card(db, user, w[0], status="review", due=NOW - timedelta(hours=1), interval=3, reps=2)
    await add_card(db, user, w[1], status="mastered", due=NOW - timedelta(days=5), interval=40, reps=6)
    await add_card(db, user, w[2], status="learning", due=NOW - timedelta(minutes=1), interval=0)
    await add_card(db, user, w[3], status="review", due=NOW + timedelta(hours=1), interval=3, reps=2)  # not due yet
    await add_card(db, user, w[4], added=NOW - timedelta(days=2))  # new, added first
    await add_card(db, user, w[5], added=NOW - timedelta(days=1))
    body = await get_session(user_client)
    assert ids(body) == [w[1].id, w[0].id, w[2].id, w[4].id, w[5].id]
    assert [c["is_new"] for c in body["cards"]] == [False, False, False, True, True]
    assert [c["status"] for c in body["cards"]] == ["mastered", "review", "learning", "new", "new"]
    assert (body["due_total"], body["new_waiting"], body["new_allowance"], body["new_today"]) == (3, 2, 20, 0)


async def test_the_daily_cap_limits_new_cards_oldest_first(user_client, db):
    fix_clock()
    user = await me(db)
    user.daily_new_cards = 3
    words = await make_words(db, 5)
    for i, w in enumerate(words):
        await add_card(db, user, w, added=NOW - timedelta(hours=10 - i))
    body = await get_session(user_client)
    assert ids(body) == [w.id for w in words[:3]]
    assert (body["new_waiting"], body["new_allowance"], body["daily_new_cards"]) == (5, 3, 3)


async def test_answering_new_cards_uses_up_the_allowance(user_client, db):
    fix_clock()
    user = await me(db)
    user.daily_new_cards = 3
    words = await make_words(db, 5)
    for i, w in enumerate(words):
        await add_card(db, user, w, added=NOW - timedelta(hours=10 - i))
    for w in words[:2]:
        assert (await answer(user_client, w, 3)).status_code == 200
    body = await get_session(user_client)
    assert body["new_today"] == 2 and body["new_allowance"] == 1
    assert ids(body) == [words[2].id]  # one more new card today, and nothing is due until tomorrow
    assert (await answer(user_client, words[2], 3)).status_code == 200
    body = await get_session(user_client)
    assert body["cards"] == [] and body["new_allowance"] == 0 and body["new_waiting"] == 2


async def test_relearning_an_old_card_does_not_use_the_new_card_allowance(user_client, db):
    fix_clock()
    user = await me(db)
    user.daily_new_cards = 1
    old, fresh = await make_words(db, 2)
    await add_card(db, user, old, status="review", due=NOW - timedelta(days=1), interval=5, reps=3)
    await add_card(db, user, fresh)
    assert (await answer(user_client, old, 1)).status_code == 200  # forgotten, back to learning
    assert (await answer(user_client, old, 3)).status_code == 200
    body = await get_session(user_client)
    assert (body["new_today"], body["new_allowance"]) == (0, 1)  # reviews are not "new"
    assert ids(body) == [fresh.id]


async def test_a_cap_of_zero_serves_reviews_only(user_client, db):
    fix_clock()
    user = await me(db)
    user.daily_new_cards = 0
    a, b = await make_words(db, 2)
    await add_card(db, user, a, status="review", due=NOW - timedelta(hours=1), interval=2, reps=2)
    await add_card(db, user, b)
    body = await get_session(user_client)
    assert ids(body) == [a.id] and (body["new_waiting"], body["new_allowance"]) == (1, 0)


async def test_the_session_limit_caps_reviews_but_not_the_count_of_due_cards(user_client, db):
    fix_clock()
    user = await me(db)
    words = await make_words(db, 6)
    for i, w in enumerate(words):
        await add_card(db, user, w, status="review", due=NOW - timedelta(hours=6 - i), interval=2, reps=2)
    body = await get_session(user_client, limit=4)
    assert ids(body) == [w.id for w in words[:4]] and body["due_total"] == 6
    assert (await user_client.get(SESSION, params={"limit": 0})).status_code == 422
    assert (await user_client.get(SESSION, params={"limit": 201})).status_code == 422


async def test_filters_by_level_and_word_list(user_client, db):
    fix_clock()
    user = await me(db)
    a1 = await make_words(db, 2, level="A1")
    b1 = await make_words(db, 2, level="B1", start=10)
    for w in a1 + b1:
        await add_card(db, user, w, status="review", due=NOW - timedelta(hours=1), interval=2, reps=2)
    new_b1 = (await make_words(db, 1, level="B1", start=20))[0]
    await add_card(db, user, new_b1)

    body = await get_session(user_client, level="B1")
    assert set(ids(body)) == {b1[0].id, b1[1].id, new_b1.id}
    assert (body["due_total"], body["new_waiting"]) == (2, 1)

    group = VocabGroup(name="Mixed")
    db.add(group)
    await db.flush()
    db.add_all(VocabGroupItem(group_id=group.id, vocabulary_id=v.id) for v in (a1[0], b1[1], new_b1))
    await db.flush()
    body = await get_session(user_client, group_id=group.id)
    assert set(ids(body)) == {a1[0].id, b1[1].id, new_b1.id}
    body = await get_session(user_client, group_id=group.id, level="A1")
    assert ids(body) == [a1[0].id]
    assert (await get_session(user_client, group_id=999_999))["cards"] == []


async def test_other_users_cards_are_never_shown(user_client, db):
    fix_clock()
    user = await me(db)
    other = await db.scalar(select(User).where(User.email == "admin@example.com"))
    mine, theirs = await make_words(db, 2)
    await add_card(db, user, mine, status="review", due=NOW - timedelta(hours=1), interval=2, reps=2)
    await add_card(db, other, theirs, status="review", due=NOW - timedelta(hours=1), interval=2, reps=2)
    assert ids(await get_session(user_client)) == [mine.id]
    assert (await answer(user_client, theirs, 3)).status_code == 404


async def test_a_card_carries_what_the_screen_needs(user_client, db):
    fix_clock()
    user = await me(db)
    (word,) = await make_words(db, 1)
    word.zhuyin, word.audio_path, word.part_of_speech = "ㄘㄜˋ", "vocabulary/ce.mp3", "noun"
    db.add_all(
        [
            VocabularyTranslation(vocabulary_id=word.id, lang="vi", meaning="kiểm tra", sort_order=0),
            VocabularyExample(vocabulary_id=word.id, hanzi_text="第二句。", sort_order=2),
            VocabularyExample(
                vocabulary_id=word.id,
                hanzi_text="第一句。",
                pinyin="dì yī jù",
                translations={"vi": "Câu một."},
                audio_path="vocabulary/examples/1.mp3",
                sort_order=1,
            ),
        ]
    )
    await add_card(db, user, word, status="review", due=NOW - timedelta(hours=1), interval=6, reps=2, ease=2.35)
    (card,) = (await get_session(user_client))["cards"]
    assert (card["traditional"], card["zhuyin"], card["part_of_speech"], card["level"]) == (
        word.traditional,
        "ㄘㄜˋ",
        "noun",
        "A1",
    )
    assert card["audio_url"] == "/audio/vocabulary/ce.mp3"
    assert card["meanings"] == {"en": [f"meaning {word.id}"], "vi": ["kiểm tra"]}
    assert card["example"] == {
        "hanzi": "第一句。",
        "pinyin": "dì yī jù",
        "zhuyin": None,
        "translations": {"vi": "Câu một."},
        "audio_url": "/audio/vocabulary/examples/1.mp3",
    }
    assert (card["interval_days"], card["repetitions"], card["is_new"]) == (6, 2, False)
    # the buttons: what each answer would do, as the scheduler computes it
    expected = srs.preview(srs.CardState("review", 2.35, 6, 2, 0, NOW - timedelta(hours=1), None, None), NOW, VN)
    assert [(n["rating"], n["interval_days"], n["due_at"]) for n in card["next"]] == [
        (r, d, due.astimezone(UTC).isoformat().replace("+00:00", "Z")) for r, (d, due) in expected.items()
    ]
    assert [n["interval_days"] for n in card["next"]][0] == 0


async def test_a_word_without_examples_or_audio_has_none(user_client, db):
    fix_clock()
    user = await me(db)
    (word,) = await make_words(db, 1)
    await add_card(db, user, word)
    (card,) = (await get_session(user_client))["cards"]
    assert card["example"] is None and card["audio_url"] is None


# ---------------------------------------------------------------------------------------------------------
# answering
# ---------------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("rating", "status", "interval", "ease"),
    [(1, "learning", 0, 2.3), (2, "review", 1, 2.35), (3, "review", 1, 2.5), (4, "review", 4, 2.65)],
)
async def test_answering_a_new_card(user_client, db, rating, status, interval, ease):
    fix_clock()
    user = await me(db)
    (word,) = await make_words(db, 1)
    await add_card(db, user, word)
    response = await answer(user_client, word, rating)
    assert response.status_code == 200
    body = response.json()
    assert (body["status"], body["interval_days"], body["ease_factor"], body["lapses"]) == (status, interval, ease, 0)
    due = datetime.fromisoformat(body["next_review_at"])
    assert due == (NOW + timedelta(minutes=10) if interval == 0 else datetime(2026, 10, 21 + interval, tzinfo=VN))

    row = await db.scalar(
        select(UserVocabProgress)
        .where(UserVocabProgress.vocabulary_id == word.id)
        .execution_options(populate_existing=True)
    )
    assert (row.status, row.interval_days, round(row.ease_factor, 2), row.repetitions) == (
        status,
        interval,
        ease,
        0 if rating == 1 else 1,
    )
    assert row.first_reviewed_at == row.last_reviewed_at == NOW
    assert row.next_review_at == due


async def test_every_answer_is_logged_with_its_rating_in_the_same_transaction(user_client, db):
    fix_clock()
    user = await me(db)
    (word,) = await make_words(db, 1)
    await add_card(db, user, word)
    await answer(user_client, word, 1)  # new -> learning
    await answer(user_client, word, 3)  # learning can be answered again at once
    logs = list(
        await db.scalars(
            select(VocabReviewLog).where(VocabReviewLog.vocabulary_id == word.id).order_by(VocabReviewLog.id)
        )
    )
    assert [(log.source, log.rating, log.reviewed_at, log.user_id) for log in logs] == [
        ("flashcard", 1, NOW, user.id),
        ("flashcard", 3, NOW, user.id),
    ]


async def test_a_failure_while_logging_leaves_the_card_untouched(user_client, db, monkeypatch):
    fix_clock()
    user = await me(db)
    (word,) = await make_words(db, 1)
    await add_card(db, user, word)

    def explode(*args, **kwargs):
        raise RuntimeError("log table unavailable")

    monkeypatch.setattr(flashcards, "VocabReviewLog", explode)
    response = await answer(user_client, word, 3)
    assert response.status_code == 500
    row = await db.scalar(
        select(UserVocabProgress)
        .where(UserVocabProgress.vocabulary_id == word.id)
        .execution_options(populate_existing=True)
    )
    assert (row.status, row.interval_days, row.first_reviewed_at) == ("new", 0, None)  # not half updated
    assert await db.scalar(select(func.count()).select_from(VocabReviewLog)) == 0


async def test_forgetting_a_known_card_is_a_lapse_and_it_can_be_relearned(user_client, db):
    fix_clock()
    user = await me(db)
    (word,) = await make_words(db, 1)
    await add_card(db, user, word, status="review", due=NOW - timedelta(hours=2), interval=10, reps=4, ease=2.5)
    failed = (await answer(user_client, word, 1)).json()
    assert (failed["status"], failed["interval_days"], failed["lapses"], failed["repetitions"]) == ("learning", 0, 1, 0)
    assert failed["ease_factor"] == 2.3
    assert (await get_session(user_client))["cards"] == []  # not due for ten minutes
    again = (await answer(user_client, word, 3)).json()  # but it may be answered now (in-session repeat)
    assert (again["status"], again["interval_days"], again["lapses"]) == ("review", 1, 1)


async def test_a_card_in_review_cannot_be_answered_before_it_is_due(user_client, db):
    fix_clock()
    user = await me(db)
    (word,) = await make_words(db, 1)
    await add_card(db, user, word, status="review", due=NOW + timedelta(days=3), interval=6, reps=2)
    response = await answer(user_client, word, 3)
    assert response.status_code == 409 and response.json()["error"]["code"] == "not_due"
    assert await db.scalar(select(func.count()).select_from(VocabReviewLog)) == 0
    row = await db.scalar(
        select(UserVocabProgress)
        .where(UserVocabProgress.vocabulary_id == word.id)
        .execution_options(populate_existing=True)
    )
    assert (row.interval_days, row.repetitions) == (6, 2)


async def test_sending_the_same_answer_twice_counts_once(user_client, db):
    fix_clock()
    user = await me(db)
    (word,) = await make_words(db, 1)
    await add_card(db, user, word, status="review", due=NOW - timedelta(hours=1), interval=6, reps=2)
    assert (await answer(user_client, word, 3)).status_code == 200
    duplicate = await answer(user_client, word, 3)  # a retry after a lost response
    assert duplicate.status_code == 409 and duplicate.json()["error"]["code"] == "not_due"
    assert await db.scalar(select(func.count()).select_from(VocabReviewLog)) == 1


async def test_cards_not_in_the_study_list_and_bad_input(user_client, db):
    fix_clock()
    (word,) = await make_words(db, 1)
    missing = await answer(user_client, word, 3)
    assert missing.status_code == 404 and missing.json()["error"]["code"] == "not_in_study_list"
    assert (await user_client.post(REVIEW, json={"vocabulary_id": 999999, "rating": 3})).status_code == 404
    for body in (
        {"vocabulary_id": word.id, "rating": 0},
        {"vocabulary_id": word.id, "rating": 5},
        {"vocabulary_id": word.id, "rating": "good"},
        {"vocabulary_id": word.id},
        {"rating": 3},
        {"vocabulary_id": word.id, "rating": 3, "extra": 1},
        {"vocabulary_id": 0, "rating": 3},
        {"vocabulary_id": 2**63, "rating": 3},
    ):
        assert (await user_client.post(REVIEW, json=body)).status_code == 422, body
    assert await db.scalar(select(func.count()).select_from(VocabReviewLog)) == 0


async def test_answers_need_the_csrf_header(user_client, db):
    fix_clock()
    user = await me(db)
    (word,) = await make_words(db, 1)
    await add_card(db, user, word)
    del user_client.headers["X-CSRF-Token"]
    response = await answer(user_client, word, 3)
    assert response.status_code == 403 and response.json()["error"]["code"] == "csrf_failed"


async def test_the_next_review_date_follows_the_users_own_day(user_client, db):
    """23:30 in Vietnam is still the 21st there, though it is 16:30 UTC; a user in Los Angeles answering
    at the same instant is on the 21st too, and gets their own midnight."""
    late = datetime(2026, 10, 21, 16, 30, tzinfo=UTC)
    fix_clock(late)
    user = await me(db)
    (word,) = await make_words(db, 1)
    await add_card(db, user, word)
    vn = datetime.fromisoformat((await answer(user_client, word, 3)).json()["next_review_at"])
    assert vn == datetime(2026, 10, 22, tzinfo=VN)

    user.timezone = "America/Los_Angeles"
    (other,) = await make_words(db, 1, start=50)
    await add_card(db, user, other)
    la = datetime.fromisoformat((await answer(user_client, other, 3)).json()["next_review_at"])
    assert la == datetime(2026, 10, 22, tzinfo=ZoneInfo("America/Los_Angeles"))


# ---------------------------------------------------------------------------------------------------------
# simultaneous answers
# ---------------------------------------------------------------------------------------------------------


@pytest.fixture
async def committed_card(engine):
    """A real committed user, word and due card (so two sessions can contend); removed afterwards."""
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as db:
        user = User(email="flash-race@example.com")
        word = Vocabulary(traditional="競", simplified="竞", pinyin="jìng", level="A1")
        db.add_all([user, word])
        await db.flush()
        db.add(
            UserVocabProgress(
                user_id=user.id,
                vocabulary_id=word.id,
                status="review",
                interval_days=6,
                repetitions=2,
                next_review_at=NOW - timedelta(hours=1),
                first_reviewed_at=NOW - timedelta(days=9),
                last_reviewed_at=NOW - timedelta(days=7),
            )
        )
        await db.commit()
        ids = (user.id, word.id)
    yield factory, ids
    async with factory() as db:
        await db.execute(delete(User).where(User.id == ids[0]))
        await db.execute(delete(Vocabulary).where(Vocabulary.id == ids[1]))
        await db.commit()


async def test_two_simultaneous_answers_to_one_card_are_applied_one_after_the_other(committed_card):
    factory, (user_id, word_id) = committed_card
    async with factory() as a, factory() as b:
        user_a, user_b = await a.get(User, user_id), await b.get(User, user_id)
        await flashcards.apply_review(a, user_a, word_id, 3, NOW)  # A has changed the card but not committed

        async def second():
            await flashcards.apply_review(b, user_b, word_id, 3, NOW)

        task = asyncio.create_task(second())
        await asyncio.sleep(0.5)
        assert not task.done(), "B must wait for A's row lock instead of reading the old state"
        await a.commit()
        with pytest.raises(AppError) as refused:
            await asyncio.wait_for(task, timeout=10)  # B now sees a card that is no longer due
        assert refused.value.code == "not_due"
    async with factory() as check:
        logs = await check.scalar(
            select(func.count()).select_from(VocabReviewLog).where(VocabReviewLog.user_id == user_id)
        )
        progress = await check.scalar(select(UserVocabProgress).where(UserVocabProgress.user_id == user_id))
        assert logs == 1 and (progress.interval_days, progress.repetitions) == (15, 3)  # counted once, 6 * 2.5


# ---------------------------------------------------------------------------------------------------------
# statistics and streaks
# ---------------------------------------------------------------------------------------------------------


def test_streak_counting():
    today = date(2026, 10, 21)
    day = lambda n: today - timedelta(days=n)  # noqa: E731
    assert streak(set(), today) == 0
    assert streak({day(0)}, today) == 1
    assert streak({day(0), day(1), day(2)}, today) == 3
    assert streak({day(1), day(2)}, today) == 2  # nothing yet today: still alive until the day ends
    assert streak({day(2), day(3)}, today) == 0  # missed yesterday: broken
    assert streak({day(0), day(1), day(3), day(4)}, today) == 2  # a gap ends it
    assert streak({day(0), day(2)}, today) == 1


async def log(db, user: User, when: datetime, *, source="flashcard", vocab: Vocabulary | None = None):
    db.add(VocabReviewLog(user_id=user.id, vocabulary_id=vocab.id, source=source, rating=3, reviewed_at=when))
    await db.flush()


async def stats_for(client) -> dict:
    response = await client.get(STATS)
    assert response.status_code == 200, response.text
    return response.json()


async def test_stats_for_a_user_with_nothing_yet(user_client):
    fix_clock()
    assert await stats_for(user_client) == {
        "due_now": 0, "new_waiting": 0, "new_allowance": 20, "new_available": 0, "new_today": 0, "daily_new_cards": 20,
        "reviewed_today": 0, "studied_today": False, "streak_days": 0, "total_cards": 0,
    }  # fmt: skip


async def test_stats_count_due_new_and_todays_work(user_client, db):
    fix_clock()
    user = await me(db)
    user.daily_new_cards = 2
    words = await make_words(db, 6)
    await add_card(db, user, words[0], status="review", due=NOW - timedelta(hours=1), interval=3, reps=2)
    await add_card(db, user, words[1], status="review", due=NOW + timedelta(days=2), interval=3, reps=2)
    for w in words[2:5]:
        await add_card(db, user, w)
    body = await stats_for(user_client)
    assert (body["due_now"], body["new_waiting"], body["new_allowance"], body["new_available"]) == (1, 3, 2, 2)
    assert body["total_cards"] == 5
    await answer(user_client, words[0], 3)
    await answer(user_client, words[2], 4)
    body = await stats_for(user_client)
    assert (body["due_now"], body["new_today"], body["new_waiting"], body["new_allowance"], body["reviewed_today"]) == (
        0,
        1,
        2,
        1,
        2,
    )
    assert (body["studied_today"], body["streak_days"]) == (True, 1)


async def test_today_is_the_users_calendar_day_not_utc(user_client, db):
    user = await me(db)
    (word,) = await make_words(db, 1)
    await add_card(db, user, word, status="review", due=NOW, interval=1, reps=1)
    # 16:30 UTC on the 21st is 23:30 in Vietnam: the 21st. 17:30 UTC is 00:30 on the 22nd.
    await log(db, user, datetime(2026, 10, 21, 16, 30, tzinfo=UTC), vocab=word)
    fix_clock(datetime(2026, 10, 21, 16, 45, tzinfo=UTC))
    assert (await stats_for(user_client))["reviewed_today"] == 1
    fix_clock(datetime(2026, 10, 21, 17, 30, tzinfo=UTC))  # the next local day has begun
    body = await stats_for(user_client)
    assert (body["reviewed_today"], body["studied_today"], body["streak_days"]) == (
        0,
        False,
        1,
    )  # yesterday keeps the streak alive


async def test_new_cards_introduced_today_restart_with_the_local_day(user_client, db):
    user = await me(db)
    user.daily_new_cards = 1
    (word,) = await make_words(db, 1)
    await add_card(db, user, word)
    fix_clock(datetime(2026, 10, 21, 16, 30, tzinfo=UTC))  # 23:30 local
    assert (await answer(user_client, word, 1)).status_code == 200
    assert (await stats_for(user_client))["new_today"] == 1
    fix_clock(datetime(2026, 10, 21, 17, 5, tzinfo=UTC))  # 00:05 local, next day
    body = await stats_for(user_client)
    assert body["new_today"] == 0 and body["new_allowance"] == 1  # a fresh cap on the new day ...
    assert body["new_waiting"] == 0 and body["new_available"] == 0  # ... but no new cards waiting
    extra = (await make_words(db, 1, start=70))[0]
    await add_card(db, user, extra, added=datetime(2026, 10, 21, 17, 0, tzinfo=UTC))
    assert (await stats_for(user_client))["new_available"] == 1  # and now there is one to offer


async def test_streak_across_days_and_sources(user_client, db):
    user = await me(db)
    (word,) = await make_words(db, 1)
    fix_clock(NOW)  # the 21st, 10:00 local
    for days_ago in (0, 1, 2, 4):  # a gap on the 3rd day back
        await log(db, user, NOW - timedelta(days=days_ago), vocab=word, source="flashcard")
    assert (await stats_for(user_client))["streak_days"] == 3
    await log(db, user, NOW - timedelta(days=3), vocab=word, source="game")  # a game fills the gap
    body = await stats_for(user_client)
    assert body["streak_days"] == 5
    assert body["reviewed_today"] == 1  # games are not flashcard answers


async def test_streak_uses_the_users_time_zone(user_client, db):
    user = await me(db)
    user.timezone = "Pacific/Kiritimati"  # UTC+14
    (word,) = await make_words(db, 1)
    now = datetime(2026, 10, 21, 12, 0, tzinfo=UTC)  # the 22nd at 02:00 there
    fix_clock(now)
    await log(db, user, datetime(2026, 10, 21, 10, 30, tzinfo=UTC), vocab=word)  # 00:30 on the 22nd there
    await log(db, user, datetime(2026, 10, 20, 12, 0, tzinfo=UTC), vocab=word)  # the 21st there
    body = await stats_for(user_client)
    assert (body["studied_today"], body["streak_days"]) == (True, 2)


async def test_an_unknown_time_zone_falls_back_to_utc(user_client, db):
    fix_clock()
    user = await me(db)
    user.timezone = "Mars/Olympus"  # cannot happen through the API, but the clock must not crash
    assert (await stats_for(user_client))["streak_days"] == 0
    assert flashcards.user_tz(user) is UTC


async def test_daily_new_cards_setting_round_trips_through_the_profile(user_client):
    assert (await user_client.get("/api/me")).json()["daily_new_cards"] == 20
    assert (await user_client.patch("/api/me", json={"daily_new_cards": 5})).json()["daily_new_cards"] == 5
    assert (await user_client.patch("/api/me", json={"daily_new_cards": 0})).json()["daily_new_cards"] == 0
    for bad in (-1, 201, "ten", None, 2.5):
        assert (await user_client.patch("/api/me", json={"daily_new_cards": bad})).status_code == 422, bad
    fix_clock()
    assert (await stats_for(user_client))["daily_new_cards"] == 0


# the streak query, checked against the plain definition ------------------------------------


async def logs_on_days(db, user, word, days_ago: list[int]) -> None:
    db.add_all(
        VocabReviewLog(
            user_id=user.id, vocabulary_id=word.id, source="flashcard", rating=3, reviewed_at=NOW - timedelta(days=d)
        )
        for d in days_ago
    )
    await db.flush()


@pytest.mark.parametrize(
    ("days_ago", "expected"),
    [
        (list(range(0, 44)), 44),  # inside the first window
        (list(range(0, 45)), 45),  # exactly fills it, and day 45 is empty
        (list(range(0, 46)), 46),  # crosses the first window
        (list(range(0, 100)), 100),  # needs the second
        (list(range(0, 100)) + list(range(101, 300)), 100),  # a gap on day 100 ends it, older days ignored
        (list(range(1, 101)), 100),  # nothing yet today: yesterday starts the streak
        (list(range(0, 44)) + [45, 46, 47], 44),  # a gap on day 44, right at the edge of the window
        (list(range(0, 45)) + [46], 45),  # a gap just past the edge
        (list(range(0, 450)), 450),  # beyond the second window
        ([2, 3, 4], 0),  # broken yesterday
    ],
)
async def test_streaks_are_exact_whatever_the_window(user_client, db, days_ago, expected):
    user = await me(db)
    (word,) = await make_words(db, 1)
    fix_clock()
    await logs_on_days(db, user, word, days_ago)
    body = await stats_for(user_client)
    assert body["streak_days"] == expected
    assert body["studied_today"] == (0 in days_ago)


async def test_the_sql_streak_agrees_with_the_plain_definition_on_random_histories(user_client, db):
    """`streak()` is the readable definition; the database does the counting. Same answer, always."""
    import random

    user = await me(db)
    (word,) = await make_words(db, 1)
    fix_clock()
    today = NOW.astimezone(VN).date()
    rng = random.Random(2026)  # noqa: S311 (test data, and the seed keeps it repeatable)
    for _ in range(40):
        await db.execute(delete(VocabReviewLog).where(VocabReviewLog.user_id == user.id))
        density = rng.choice([0.3, 0.6, 0.9, 0.98, 1.0])
        days_ago = [d for d in range(0, rng.choice([5, 30, 120])) if rng.random() < density]
        await logs_on_days(db, user, word, days_ago)
        days = {today - timedelta(days=d) for d in days_ago}
        body = await stats_for(user_client)
        assert body["streak_days"] == streak(days, today), sorted(days_ago)
        assert body["studied_today"] == (0 in days_ago)


@pytest.mark.parametrize(
    "zone", ["GB", "ROC", "Brazil/West", "Asia/Ashkhabad", "America/Catamarca", "Etc/GMT+12", "Asia/Kathmandu"]
)
async def test_zones_that_postgres_may_not_know_still_work(user_client, db, zone):
    """The profile accepts every name Python's tz data has, including legacy aliases this Postgres lacks;
    days are bounded in Python, so those users must get statistics like everyone else."""
    user = await me(db)
    user.timezone = zone
    (word,) = await make_words(db, 1)
    fix_clock()
    await logs_on_days(db, user, word, [0, 1, 2])
    body = await stats_for(user_client)
    assert (body["studied_today"], body["streak_days"]) == (True, 3)


async def test_no_zone_python_accepts_breaks_the_day_boundaries():
    from zoneinfo import available_timezones

    for name in sorted(available_timezones()):
        tz = ZoneInfo(name)
        start, end = flashcards.day_bounds(NOW, tz)
        assert start < NOW <= end or start <= NOW < end, name
        starts, ends = flashcards._day_boundaries(NOW.astimezone(tz).date(), tz, 3)
        assert starts[0] == start and ends[0] == end and ends[1] == starts[0], name  # days tile without gaps
