from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ExampleOut(BaseModel):
    hanzi: str
    pinyin: str | None
    zhuyin: str | None
    translations: dict[str, str]
    audio_url: str | None


class NextOut(BaseModel):
    """What answering with `rating` would do: the button label and the due time."""

    rating: Literal[1, 2, 3, 4]
    interval_days: int  # 0 means minutes
    due_at: datetime


class CardOut(BaseModel):
    vocabulary_id: int
    traditional: str
    simplified: str
    pinyin: str
    zhuyin: str | None
    part_of_speech: str | None
    level: str
    audio_url: str | None
    meanings: dict[str, list[str]]
    example: ExampleOut | None
    status: str
    is_new: bool
    interval_days: int
    repetitions: int
    next: list[NextOut]


class SessionOut(BaseModel):
    cards: list[CardOut]  # due reviews first (most overdue first), then new cards
    due_total: int  # due reviews matching the filters, before the session limit
    new_waiting: int  # new cards matching the filters, whatever the daily cap
    new_allowance: int  # what the daily cap still allows today, whatever is waiting
    new_today: int
    daily_new_cards: int


class ReviewIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    vocabulary_id: int = Field(ge=1, le=2**63 - 1)
    rating: Literal[1, 2, 3, 4]  # 1 again, 2 hard, 3 good, 4 easy


class ReviewOut(BaseModel):
    vocabulary_id: int
    status: str
    interval_days: int
    repetitions: int
    lapses: int
    ease_factor: float
    next_review_at: datetime


class StatsOut(BaseModel):
    due_now: int
    new_waiting: int  # new cards in the study list
    new_allowance: int  # what the daily cap still allows today
    new_available: int  # what a session would offer: the smaller of the two
    new_today: int
    daily_new_cards: int
    reviewed_today: int  # flashcard answers today
    studied_today: bool  # any review today, flashcard or game
    streak_days: int
    total_cards: int
