import pytest
from sqlalchemy import func, select

from app.models import (
    Lesson,
    LessonSegment,
    QuestionChoice,
    SegmentVocabulary,
    User,
    Vocabulary,
    VocabularyExample,
    VocabularyTranslation,
)
from app.seed import seed, word_spans
from app.services.passwords import verify_password


async def test_seed_contents(db, seeded):
    assert await db.scalar(select(func.count()).select_from(Vocabulary)) >= 20
    levels = set(await db.scalars(select(Vocabulary.level).distinct()))
    assert levels == {"A1", "A2", "B1", "B2", "C1", "C2"}
    # Every word has vi and en meanings; most have an example.
    langs = await db.execute(
        select(VocabularyTranslation.vocabulary_id, func.array_agg(VocabularyTranslation.lang)).group_by(
            VocabularyTranslation.vocabulary_id
        )
    )
    assert all(sorted(lang) == ["en", "vi"] for _, lang in langs)
    assert await db.scalar(select(func.count()).select_from(VocabularyExample)) >= 10
    assert sorted(await db.scalars(select(Lesson.type))) == ["dictation", "listening", "reading"]


async def test_seed_is_a_no_op_the_second_time(db, seeded):
    assert await seed(db) is False


async def test_polyphones_and_normalized_pinyin(db, seeded):
    rows = dict(
        (
            await db.execute(
                select(Vocabulary.pinyin, Vocabulary.pinyin_normalized).where(
                    Vocabulary.traditional.in_(["行", "女", "綠", "你好"])
                )
            )
        ).all()
    )
    assert rows == {"xíng": "xing", "háng": "hang", "nǚ": "nu", "lǜ": "lu", "nǐ hǎo": "nihao"}


async def test_every_question_has_exactly_one_correct_choice(db, seeded):
    counts = await db.scalars(
        select(func.count().filter(QuestionChoice.is_correct)).group_by(QuestionChoice.question_id)
    )
    assert set(counts) == {1}


async def test_segment_offsets_point_at_their_words(db, seeded):
    rows = await db.execute(
        select(
            LessonSegment.hanzi_text, SegmentVocabulary.char_start, SegmentVocabulary.char_end, Vocabulary.traditional
        )
        .join(SegmentVocabulary, SegmentVocabulary.segment_id == LessonSegment.id)
        .join(Vocabulary, Vocabulary.id == SegmentVocabulary.vocabulary_id)
    )
    rows = rows.all()
    assert rows
    for hanzi, start, end, word in rows:
        assert hanzi[start:end] == word


async def test_audio_segments_are_timed_and_reading_segments_are_not(db, seeded):
    rows = await db.execute(select(Lesson.type, LessonSegment.start_ms, LessonSegment.end_ms).join(LessonSegment))
    for lesson_type, start, end in rows:
        if lesson_type == "reading":
            assert start is None and end is None
        else:
            assert start is not None and end > start


async def test_seed_users_can_use_the_documented_password(db, seeded):
    user = await db.scalar(select(User).where(User.email == "test@example.com"))
    assert verify_password(user.password_hash, "password123")


def test_word_spans_uses_code_point_offsets():
    assert word_spans("我每天學習中文。", ["我", "學習", "中文"]) == [(0, 1, "我"), (3, 5, "學習"), (5, 7, "中文")]
    # A character outside the BMP still counts as one position.
    assert word_spans("𠮷野家很好", ["很"]) == [(3, 4, "很")]
    with pytest.raises(ValueError):
        word_spans("你好", ["謝謝"])
