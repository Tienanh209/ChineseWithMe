from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, Boolean, ForeignKey, Integer, SmallInteger, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import (
    Base,
    CefrLevel,
    LessonType,
    created_at_column,
    db_default,
    id_column,
    updated_at_column,
)


class LessonCategory(Base):
    __tablename__ = "lesson_categories"

    id: Mapped[int] = id_column()
    name: Mapped[str] = mapped_column(Text)
    level: Mapped[str] = mapped_column(CefrLevel)
    description: Mapped[str | None] = mapped_column(Text)
    sort_order: Mapped[int] = mapped_column(Integer, server_default=db_default())


class Lesson(Base):
    __tablename__ = "lessons"

    id: Mapped[int] = id_column()
    # ON DELETE RESTRICT: a category with lessons cannot be deleted.
    category_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("lesson_categories.id", ondelete="RESTRICT"))
    type: Mapped[str] = mapped_column(LessonType)
    level: Mapped[str] = mapped_column(CefrLevel)  # app rule: equals the category level
    title: Mapped[str] = mapped_column(Text)
    audio_path: Mapped[str | None] = mapped_column(Text)
    duration_seconds: Mapped[int | None] = mapped_column(Integer)
    sort_order: Mapped[int] = mapped_column(Integer, server_default=db_default())
    is_published: Mapped[bool] = mapped_column(Boolean, server_default=db_default())
    created_at: Mapped[datetime] = created_at_column()
    updated_at: Mapped[datetime] = updated_at_column()

    segments: Mapped[list["LessonSegment"]] = relationship(
        lazy="raise", passive_deletes=True, order_by="LessonSegment.sequence_order"
    )
    questions: Mapped[list["Question"]] = relationship(
        lazy="raise", passive_deletes=True, order_by="Question.sequence_order"
    )


class LessonSegment(Base):
    __tablename__ = "lesson_segments"

    id: Mapped[int] = id_column()
    lesson_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("lessons.id", ondelete="CASCADE"))
    sequence_order: Mapped[int] = mapped_column(Integer)
    start_ms: Mapped[int | None] = mapped_column(Integer)
    end_ms: Mapped[int | None] = mapped_column(Integer)
    hanzi_text: Mapped[str] = mapped_column(Text)
    pinyin: Mapped[str | None] = mapped_column(Text)
    zhuyin: Mapped[str | None] = mapped_column(Text)
    translations: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=db_default())

    words: Mapped[list["SegmentVocabulary"]] = relationship(
        lazy="raise", passive_deletes=True, order_by="SegmentVocabulary.char_start"
    )


class SegmentVocabulary(Base):
    """A word inside a segment. char_start/char_end: 0-based, end-exclusive code point offsets."""

    __tablename__ = "segment_vocabulary"

    segment_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("lesson_segments.id", ondelete="CASCADE"), primary_key=True
    )
    char_start: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    char_end: Mapped[int] = mapped_column(SmallInteger)
    vocabulary_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("vocabulary.id", ondelete="CASCADE"))


class Question(Base):
    __tablename__ = "questions"

    id: Mapped[int] = id_column()
    lesson_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("lessons.id", ondelete="CASCADE"))
    sequence_order: Mapped[int] = mapped_column(Integer)
    prompt: Mapped[str] = mapped_column(Text)
    audio_path: Mapped[str | None] = mapped_column(Text)
    explanation: Mapped[str | None] = mapped_column(Text)

    choices: Mapped[list["QuestionChoice"]] = relationship(
        lazy="raise", passive_deletes=True, order_by="QuestionChoice.sequence_order"
    )


class QuestionChoice(Base):
    __tablename__ = "question_choices"

    id: Mapped[int] = id_column()
    question_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("questions.id", ondelete="CASCADE"))
    sequence_order: Mapped[int] = mapped_column(SmallInteger)
    choice_text: Mapped[str] = mapped_column(Text)
    is_correct: Mapped[bool] = mapped_column(Boolean, server_default=db_default())
