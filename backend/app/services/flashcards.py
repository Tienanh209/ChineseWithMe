"""Flashcard sessions, answers and statistics (FEATURES.md M3).

"Today" is the user's own calendar day (users.timezone). A card is due when its next_review_at has
passed; cards still 'new' are handed out up to the user's daily cap, counted by first_reviewed_at.
"""

from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta, tzinfo
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import Select, exists, func, select, text
from sqlalchemy.dialects.postgresql import distinct_on
from sqlalchemy.ext.asyncio import AsyncSession

from app.errors import AppError
from app.models import (
    User,
    UserVocabProgress,
    VocabGroupItem,
    VocabReviewLog,
    Vocabulary,
    VocabularyExample,
)
from app.services import srs
from app.services.vocab_search import load_meanings

# A streak is counted over this many days at most.
STREAK_LOOKBACK_DAYS = 1100
DEFAULT_SESSION_LIMIT = 50


def user_tz(user: User) -> tzinfo:
    try:
        return ZoneInfo(user.timezone)
    except (ZoneInfoNotFoundError, ValueError):
        return UTC


def day_bounds(now: datetime, tz: tzinfo) -> tuple[datetime, datetime]:
    """Start (inclusive) and end (exclusive) of the user's current day, as UTC instants."""
    today = now.astimezone(tz).date()
    start = datetime.combine(today, time.min, tzinfo=tz)
    end = datetime.combine(today + timedelta(days=1), time.min, tzinfo=tz)
    return start.astimezone(UTC), end.astimezone(UTC)


def streak(days: set[date], today: date) -> int:
    """Consecutive days of activity ending today, or yesterday when today has none yet (the streak is
    still alive until the day is over). Zero when neither day has any."""
    day = today if today in days else today - timedelta(days=1)
    count = 0
    while day in days:
        count += 1
        day -= timedelta(days=1)
    return count


def to_state(progress: UserVocabProgress) -> srs.CardState:
    return srs.CardState(
        status=progress.status,  # type: ignore[arg-type]
        ease_factor=round(float(progress.ease_factor), 2),  # REAL is float32: 2.35 comes back 2.3499999
        interval_days=progress.interval_days,
        repetitions=progress.repetitions,
        lapses=progress.lapses,
        next_review_at=progress.next_review_at,
        last_reviewed_at=progress.last_reviewed_at,
        first_reviewed_at=progress.first_reviewed_at,
    )


def _for_user(stmt: Select, user_id: int, level: str | None, group_id: int | None) -> Select:
    stmt = stmt.where(UserVocabProgress.user_id == user_id)
    if level is not None or group_id is not None:
        stmt = stmt.join(Vocabulary, Vocabulary.id == UserVocabProgress.vocabulary_id)
    if level is not None:
        stmt = stmt.where(Vocabulary.level == level)
    if group_id is not None:
        stmt = stmt.where(
            UserVocabProgress.vocabulary_id.in_(
                select(VocabGroupItem.vocabulary_id).where(VocabGroupItem.group_id == group_id)
            )
        )
    return stmt


def _due_review_condition(now: datetime):
    return (UserVocabProgress.status != "new") & (UserVocabProgress.next_review_at <= now)


async def new_cards_today(db: AsyncSession, user_id: int, start: datetime, end: datetime) -> int:
    return (
        await db.scalar(
            select(func.count()).where(
                UserVocabProgress.user_id == user_id,
                UserVocabProgress.first_reviewed_at >= start,
                UserVocabProgress.first_reviewed_at < end,
            )
        )
        or 0
    )


@dataclass
class SessionData:
    reviews: list[tuple[UserVocabProgress, Vocabulary]]
    new: list[tuple[UserVocabProgress, Vocabulary]]
    meanings: dict[int, dict[str, list[str]]]
    examples: dict[int, VocabularyExample]
    due_total: int
    new_waiting: int
    new_allowance: int
    new_today: int
    now: datetime
    tz: tzinfo


async def build_session(
    db: AsyncSession,
    user: User,
    now: datetime,
    *,
    level: str | None,
    group_id: int | None,
    limit: int = DEFAULT_SESSION_LIMIT,
) -> SessionData:
    tz = user_tz(user)
    start, end = day_bounds(now, tz)
    new_today = await new_cards_today(db, user.id, start, end)
    allowance = max(0, user.daily_new_cards - new_today)

    def count(*conditions) -> Select:
        return _for_user(select(func.count()).select_from(UserVocabProgress), user.id, level, group_id).where(
            *conditions
        )

    due_total = await db.scalar(count(_due_review_condition(now))) or 0
    new_waiting = await db.scalar(count(UserVocabProgress.status == "new")) or 0

    def cards(*conditions, order, take: int) -> Select:
        stmt = _for_user(select(UserVocabProgress, Vocabulary), user.id, level, group_id)
        if level is None and group_id is None:  # _for_user only joins when it filters
            stmt = stmt.join(Vocabulary, Vocabulary.id == UserVocabProgress.vocabulary_id)
        return stmt.where(*conditions).order_by(*order).limit(take)

    reviews = [
        (p, v)
        for p, v in (
            await db.execute(
                cards(
                    _due_review_condition(now),
                    order=(UserVocabProgress.next_review_at, UserVocabProgress.vocabulary_id),
                    take=limit,
                )
            )
        ).all()
    ]
    take_new = min(allowance, new_waiting)
    new = (
        [
            (p, v)
            for p, v in (
                await db.execute(
                    cards(
                        UserVocabProgress.status == "new",
                        order=(UserVocabProgress.next_review_at, UserVocabProgress.vocabulary_id),
                        take=take_new,
                    )
                )
            ).all()
        ]
        if take_new
        else []
    )

    ids = [v.id for _, v in reviews + new]
    meanings = await load_meanings(db, ids)
    examples: dict[int, VocabularyExample] = {}
    if ids:
        first_example = (
            select(VocabularyExample)
            .ext(distinct_on(VocabularyExample.vocabulary_id))
            .where(VocabularyExample.vocabulary_id.in_(ids))
            .order_by(VocabularyExample.vocabulary_id, VocabularyExample.sort_order, VocabularyExample.id)
        )
        examples = {e.vocabulary_id: e for e in await db.scalars(first_example)}
    return SessionData(reviews, new, meanings, examples, due_total, new_waiting, allowance, new_today, now, tz)


async def apply_review(
    db: AsyncSession, user: User, vocabulary_id: int, rating: int, now: datetime
) -> UserVocabProgress:
    """Answer one card. The card's new state and the review log are written together or not at all.

    The row is locked first, so two simultaneous answers to one card (two tabs, a retry) are applied
    one after the other: the second sees the first's result and, if the card is no longer due, is
    refused instead of double counting.
    """
    progress = await db.scalar(
        select(UserVocabProgress)
        .where(UserVocabProgress.user_id == user.id, UserVocabProgress.vocabulary_id == vocabulary_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if progress is None:
        raise AppError(404, "not_in_study_list", "That word is not in your study list.")
    # New cards and cards being relearned (a few minutes after "again") can be answered at any time;
    # a card in review only once it is due.
    if progress.status in ("review", "mastered") and progress.next_review_at > now:
        raise AppError(409, "not_due", "This card is not due yet.")

    after = srs.schedule(to_state(progress), rating, now, user_tz(user))
    async with db.begin_nested():
        progress.status = after.status
        progress.ease_factor = after.ease_factor
        progress.interval_days = after.interval_days
        progress.repetitions = after.repetitions
        progress.lapses = after.lapses
        progress.next_review_at = after.next_review_at
        progress.last_reviewed_at = after.last_reviewed_at
        progress.first_reviewed_at = after.first_reviewed_at
        db.add(
            VocabReviewLog(
                user_id=user.id, vocabulary_id=vocabulary_id, source="flashcard", rating=rating, reviewed_at=now
            )
        )
        await db.flush()
    return progress


@dataclass
class Stats:
    due_now: int
    new_waiting: int
    new_allowance: int
    new_available: int
    new_today: int
    daily_new_cards: int
    reviewed_today: int
    studied_today: bool
    streak_days: int
    total_cards: int


# Days are bounded in Python (zoneinfo) and handed to the database as instants. Postgres is never given a
# time zone NAME: its tz data can lack aliases (GB, ROC, Brazil/West) that the profile accepts.
#
# Walks back one day at a time, one index probe each, while every day has a review. $1/$2 are the UTC
# start and end of day 0, 1, 2 ... going back from the anchor. Cost grows with the streak, not with the
# number of reviews the user has ever done.
_STREAK_SQL = text(
    """
WITH RECURSIVE walk(k) AS (
    SELECT 1 WHERE EXISTS (
        SELECT 1 FROM vocab_review_logs l
        WHERE l.user_id = :uid AND l.reviewed_at >= (CAST(:starts AS timestamptz[]))[1]
                               AND l.reviewed_at <  (CAST(:ends AS timestamptz[]))[1])
  UNION ALL
    SELECT w.k + 1 FROM walk w
    WHERE w.k < cardinality(CAST(:starts AS timestamptz[])) AND EXISTS (
        SELECT 1 FROM vocab_review_logs l
        WHERE l.user_id = :uid AND l.reviewed_at >= (CAST(:starts AS timestamptz[]))[w.k + 1]
                               AND l.reviewed_at <  (CAST(:ends AS timestamptz[]))[w.k + 1])
)
SELECT count(*) FROM walk
"""
)
STREAK_CHUNK_DAYS = 60  # boundaries are built in chunks, so a short streak builds only one


def _day_boundaries(newest: date, tz: tzinfo, days: int) -> tuple[list[datetime], list[datetime]]:
    """UTC [start, end) of `days` consecutive local days, going back from `newest`."""
    starts, ends = [], []
    for k in range(days):
        day = newest - timedelta(days=k)
        starts.append(datetime.combine(day, time.min, tzinfo=tz).astimezone(UTC))
        ends.append(datetime.combine(day + timedelta(days=1), time.min, tzinfo=tz).astimezone(UTC))
    return starts, ends


async def streak_info(db: AsyncSession, user: User, now: datetime, tz: tzinfo) -> tuple[bool, int]:
    """(studied today, streak in days) in the user's own days. The streak ends today, or yesterday while
    today is still empty. Counted over at most STREAK_LOOKBACK_DAYS."""
    today = now.astimezone(tz).date()
    start, end = day_bounds(now, tz)
    studied_today = bool(
        await db.scalar(
            select(
                exists().where(
                    VocabReviewLog.user_id == user.id,
                    VocabReviewLog.reviewed_at >= start,
                    VocabReviewLog.reviewed_at < end,
                )
            )
        )
    )
    newest = today if studied_today else today - timedelta(days=1)
    length = 0
    while length < STREAK_LOOKBACK_DAYS:
        chunk = min(STREAK_CHUNK_DAYS, STREAK_LOOKBACK_DAYS - length)
        starts, ends = _day_boundaries(newest - timedelta(days=length), tz, chunk)
        counted = int(await db.scalar(_STREAK_SQL, {"uid": user.id, "starts": starts, "ends": ends}) or 0)
        length += counted
        if counted < chunk:
            break  # a day without a review: the streak ends here
    return studied_today, length


async def stats(db: AsyncSession, user: User, now: datetime) -> Stats:
    tz = user_tz(user)
    start, end = day_bounds(now, tz)
    new_today = await new_cards_today(db, user.id, start, end)

    async def count(*conditions) -> int:
        return (
            await db.scalar(
                select(func.count())
                .select_from(UserVocabProgress)
                .where(UserVocabProgress.user_id == user.id, *conditions)
            )
            or 0
        )

    new_waiting = await count(UserVocabProgress.status == "new")
    reviewed_today = (
        await db.scalar(
            select(func.count()).where(
                VocabReviewLog.user_id == user.id,
                VocabReviewLog.source == "flashcard",
                VocabReviewLog.reviewed_at >= start,
                VocabReviewLog.reviewed_at < end,
            )
        )
        or 0
    )
    studied_today, streak_days = await streak_info(db, user, now, tz)
    allowance = max(0, user.daily_new_cards - new_today)
    return Stats(
        due_now=await count(_due_review_condition(now)),
        new_waiting=new_waiting,
        new_allowance=allowance,
        new_available=min(allowance, new_waiting),
        new_today=new_today,
        daily_new_cards=user.daily_new_cards,
        reviewed_today=reviewed_today,
        studied_today=studied_today,
        streak_days=streak_days,
        total_cards=await count(),
    )
