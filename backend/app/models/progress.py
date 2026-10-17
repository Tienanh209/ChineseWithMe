from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    REAL,
    BigInteger,
    Boolean,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    Numeric,
    SmallInteger,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, CefrLevel, db_default, id_column


def _user_fk():
    return mapped_column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"))


class UserVocabProgress(Base):
    """SM-2 state, one row per user and word."""

    __tablename__ = "user_vocab_progress"

    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    vocabulary_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("vocabulary.id", ondelete="CASCADE"), primary_key=True
    )
    status: Mapped[str] = mapped_column(Text, server_default=db_default())
    ease_factor: Mapped[float] = mapped_column(REAL, server_default=db_default())
    interval_days: Mapped[int] = mapped_column(Integer, server_default=db_default())
    repetitions: Mapped[int] = mapped_column(Integer, server_default=db_default())
    lapses: Mapped[int] = mapped_column(Integer, server_default=db_default())
    next_review_at: Mapped[datetime] = mapped_column(server_default=db_default())
    last_reviewed_at: Mapped[datetime | None]


class VocabReviewLog(Base):
    __tablename__ = "vocab_review_logs"

    id: Mapped[int] = id_column()
    user_id: Mapped[int] = _user_fk()
    vocabulary_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("vocabulary.id", ondelete="CASCADE"))
    source: Mapped[str] = mapped_column(Text)  # 'flashcard' | 'game'
    rating: Mapped[int] = mapped_column(SmallInteger)  # 1 again, 2 hard, 3 good, 4 easy
    reviewed_at: Mapped[datetime] = mapped_column(server_default=db_default())


class UserLessonProgress(Base):
    __tablename__ = "user_lesson_progress"

    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    lesson_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("lessons.id", ondelete="CASCADE"), primary_key=True)
    status: Mapped[str] = mapped_column(Text, server_default=db_default())  # set completed_at with 'completed'
    last_position_ms: Mapped[int] = mapped_column(Integer, server_default=db_default())
    completed_at: Mapped[datetime | None]
    updated_at: Mapped[datetime] = mapped_column(server_default=db_default(), server_onupdate=db_default())


class ExerciseAttempt(Base):
    __tablename__ = "exercise_attempts"

    id: Mapped[int] = id_column()
    user_id: Mapped[int] = _user_fk()
    lesson_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("lessons.id", ondelete="CASCADE"))
    total: Mapped[int] = mapped_column(SmallInteger)
    score: Mapped[int | None] = mapped_column(SmallInteger)
    started_at: Mapped[datetime] = mapped_column(server_default=db_default())
    finished_at: Mapped[datetime | None]


class ExerciseAnswer(Base):
    __tablename__ = "exercise_answers"
    __table_args__ = (
        # The chosen option must belong to the question it answers.
        ForeignKeyConstraint(
            ["choice_id", "question_id"],
            ["question_choices.id", "question_choices.question_id"],
            ondelete="CASCADE",
        ),
    )

    attempt_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("exercise_attempts.id", ondelete="CASCADE"), primary_key=True
    )
    question_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("questions.id", ondelete="CASCADE"), primary_key=True
    )
    choice_id: Mapped[int] = mapped_column(BigInteger)
    is_correct: Mapped[bool] = mapped_column(Boolean)


class GameSession(Base):
    __tablename__ = "game_sessions"

    id: Mapped[int] = id_column()
    user_id: Mapped[int] = _user_fk()
    game_type: Mapped[str] = mapped_column(Text)
    group_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("vocab_groups.id", ondelete="SET NULL"))
    level: Mapped[str | None] = mapped_column(CefrLevel)
    score: Mapped[int] = mapped_column(Integer, server_default=db_default())
    correct_count: Mapped[int] = mapped_column(SmallInteger, server_default=db_default())
    total_count: Mapped[int] = mapped_column(SmallInteger, server_default=db_default())
    duration_seconds: Mapped[int | None] = mapped_column(Integer)
    played_at: Mapped[datetime] = mapped_column(server_default=db_default())


class DictationAttempt(Base):
    __tablename__ = "dictation_attempts"

    id: Mapped[int] = id_column()
    user_id: Mapped[int] = _user_fk()
    segment_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("lesson_segments.id", ondelete="CASCADE"))
    user_input: Mapped[str] = mapped_column(Text)
    is_correct: Mapped[bool] = mapped_column(Boolean)
    accuracy: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    created_at: Mapped[datetime] = mapped_column(server_default=db_default())
