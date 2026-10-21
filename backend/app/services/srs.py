"""Spaced repetition scheduling: SM-2 with four ratings. Pure: no database, no clock, no globals.

Ratings: 1 again, 2 hard, 3 good, 4 easy.

A card is `new` until its first review, `learning` after an "again" (due again in 10 minutes), `review`
while its interval is under 21 days and `mastered` from 21 days on.

Intervals, by repetitions so far (`ease` is the card's ease factor, never below 1.3, starts at 2.5):

            first review   second review   later
  again     10 minutes     10 minutes      10 minutes         ease - 0.20, repetitions back to 0
  hard      1 day          interval * 1.2  (at least +1 day)  ease - 0.15
  good      1 day          6 days          interval * ease    (at least +1 day)
  easy      4 days         good + more     interval * ease * 1.3 (at least good + 1)   ease + 0.15

"again" on a card that had reached review counts as a lapse; on a new or learning card it does not.

Review dates are the START of a local day, `interval` days ahead, not "24 hours from now". A card
reviewed at 9:05 with a 1 day interval is due from midnight, so someone who studies at 9:00 every
morning sees it. Only "again" uses a time of day, and it is never later than the start of tomorrow.
"""

from dataclasses import dataclass, replace
from datetime import datetime, time, timedelta, tzinfo
from typing import Literal

Status = Literal["new", "learning", "review", "mastered"]

EASE_START = 2.5
EASE_MIN = 1.3
AGAIN_DELAY = timedelta(minutes=10)
MASTERED_DAYS = 21
MAX_INTERVAL_DAYS = 3650  # ten years; keeps dates and the INTEGER column safe

AGAIN, HARD, GOOD, EASY = 1, 2, 3, 4
RATINGS = (AGAIN, HARD, GOOD, EASY)


@dataclass(frozen=True)
class CardState:
    status: Status = "new"
    ease_factor: float = EASE_START
    interval_days: int = 0
    repetitions: int = 0
    lapses: int = 0
    next_review_at: datetime | None = None
    last_reviewed_at: datetime | None = None
    first_reviewed_at: datetime | None = None


def _ease(value: float) -> float:
    # Rounded so float32 storage and repeated arithmetic never drift: 2.5 - 0.15 stays 2.35.
    return round(max(EASE_MIN, value), 2)


def _status(interval_days: int) -> Status:
    if interval_days == 0:
        return "learning"
    return "mastered" if interval_days >= MASTERED_DAYS else "review"


def _good_interval(state: CardState) -> int:
    if state.repetitions == 0:
        return 1
    if state.repetitions == 1:
        return 6
    return max(state.interval_days + 1, round(state.interval_days * state.ease_factor))


def _next_interval(state: CardState, rating: int) -> tuple[int, float]:
    """(new interval in days, new ease factor)."""
    if rating == AGAIN:
        return 0, _ease(state.ease_factor - 0.20)
    if rating == HARD:
        interval = 1 if state.repetitions == 0 else max(state.interval_days + 1, round(state.interval_days * 1.2))
        return min(interval, MAX_INTERVAL_DAYS), _ease(state.ease_factor - 0.15)
    good = _good_interval(state)
    if rating == GOOD:
        return min(good, MAX_INTERVAL_DAYS), state.ease_factor
    ease = _ease(state.ease_factor + 0.15)
    if state.repetitions == 0:
        return 4, ease
    easy = max(good + 1, round(max(state.interval_days, 1) * ease * 1.3))
    return min(easy, MAX_INTERVAL_DAYS), ease


def _start_of_day(now: datetime, tz: tzinfo, days_ahead: int) -> datetime:
    local_date = now.astimezone(tz).date() + timedelta(days=days_ahead)
    return datetime.combine(local_date, time.min, tzinfo=tz)


def _due(interval_days: int, now: datetime, tz: tzinfo) -> datetime:
    if interval_days == 0:
        # Ten minutes, but never later than tomorrow's start: answered at 23:55, "again" must not
        # come back after "hard" (1 day) does.
        return min(now + AGAIN_DELAY, _start_of_day(now, tz, 1))
    return _start_of_day(now, tz, interval_days)


def schedule(state: CardState, rating: int, now: datetime, tz: tzinfo) -> CardState:
    """The card after being answered with `rating` at `now`, for a user whose day follows `tz`."""
    if rating not in RATINGS:
        raise ValueError(f"rating must be 1, 2, 3 or 4, not {rating!r}")
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")

    interval, ease = _next_interval(state, rating)
    lapsed = rating == AGAIN and state.interval_days >= 1
    return replace(
        state,
        status=_status(interval),
        ease_factor=ease,
        interval_days=interval,
        repetitions=0 if rating == AGAIN else state.repetitions + 1,
        lapses=state.lapses + (1 if lapsed else 0),
        next_review_at=_due(interval, now, tz),
        last_reviewed_at=now,
        first_reviewed_at=state.first_reviewed_at or now,
    )


def preview(state: CardState, now: datetime, tz: tzinfo) -> dict[int, tuple[int, datetime]]:
    """For each rating, the interval in days (0 = minutes) and the due time it would give: what the
    buttons show ("10 min", "1 day", "6 days")."""
    out = {}
    for rating in RATINGS:
        after = schedule(state, rating, now, tz)
        assert after.next_review_at is not None
        out[rating] = (after.interval_days, after.next_review_at)
    return out
