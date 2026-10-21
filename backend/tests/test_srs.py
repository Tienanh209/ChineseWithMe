from dataclasses import replace
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from app.services.srs import (
    AGAIN,
    EASE_MIN,
    EASE_START,
    EASY,
    GOOD,
    HARD,
    MAX_INTERVAL_DAYS,
    RATINGS,
    CardState,
    preview,
    schedule,
)

VN = ZoneInfo("Asia/Ho_Chi_Minh")  # UTC+7, no DST
NOW = datetime(2026, 10, 21, 8, 5, tzinfo=VN)  # 09:05 would also do: the time of day must not matter


def review(state: CardState, *ratings: int, now: datetime = NOW, tz=VN) -> CardState:
    for rating in ratings:
        state = schedule(state, rating, now, tz)
    return state


def local_midnight(days_ahead: int, tz=VN, now: datetime = NOW) -> datetime:
    day = now.astimezone(tz).date() + timedelta(days=days_ahead)
    return datetime(day.year, day.month, day.day, tzinfo=tz)


# the first review of a new card -----------------------------------------------------------------


def test_a_new_card_answered_again_comes_back_in_ten_minutes():
    card = schedule(CardState(), AGAIN, NOW, VN)
    assert (card.status, card.interval_days, card.repetitions, card.lapses) == ("learning", 0, 0, 0)
    assert card.ease_factor == 2.3
    assert card.next_review_at == NOW + timedelta(minutes=10)
    assert (card.last_reviewed_at, card.first_reviewed_at) == (NOW, NOW)


@pytest.mark.parametrize(
    ("rating", "interval", "ease"),
    [(HARD, 1, 2.35), (GOOD, 1, 2.5), (EASY, 4, 2.65)],
)
def test_first_review_intervals_and_ease(rating, interval, ease):
    card = schedule(CardState(), rating, NOW, VN)
    assert (card.status, card.interval_days, card.repetitions, card.lapses) == ("review", interval, 1, 0)
    assert card.ease_factor == ease
    assert card.next_review_at == local_midnight(interval)


# a card growing up ----------------------------------------------------------------------------------


def test_good_good_good_follows_one_six_then_ease_multiples():
    card = CardState()
    seen = []
    for _ in range(6):
        card = schedule(card, GOOD, NOW, VN)
        seen.append((card.interval_days, card.status))
    assert [i for i, _ in seen] == [1, 6, 15, 38, 95, 238]  # 1, 6, 6*2.5, 15*2.5, 38*2.5, 95*2.5
    assert [s for _, s in seen] == ["review", "review", "review", "mastered", "mastered", "mastered"]
    assert card.ease_factor == EASE_START  # "good" leaves the ease alone
    assert card.repetitions == 6


def test_hard_slows_growth_and_lowers_ease():
    card = review(CardState(), GOOD, GOOD)  # interval 6
    hard = schedule(card, HARD, NOW, VN)
    assert hard.interval_days == 7  # 6 * 1.2 = 7.2 -> 7
    assert hard.ease_factor == 2.35
    again_hard = schedule(replace(card, interval_days=1, repetitions=2), HARD, NOW, VN)
    assert again_hard.interval_days == 2  # always at least a day more


def test_easy_beats_good_and_raises_ease():
    card = review(CardState(), GOOD, GOOD)
    easy = schedule(card, EASY, NOW, VN)
    assert easy.interval_days == round(6 * 2.65 * 1.3)  # 21
    assert easy.ease_factor == 2.65
    assert easy.interval_days > schedule(card, GOOD, NOW, VN).interval_days
    assert easy.status == "mastered"  # 21 days


def test_a_second_easy_is_longer_than_a_second_good():
    first = schedule(CardState(), GOOD, NOW, VN)  # interval 1, one repetition
    assert schedule(first, GOOD, NOW, VN).interval_days == 6
    assert schedule(first, EASY, NOW, VN).interval_days == 7  # never below good + 1


# forgetting ---------------------------------------------------------------------------------------------


def test_forgetting_a_known_card_is_a_lapse_and_restarts_it():
    card = review(CardState(), GOOD, GOOD, GOOD)  # interval 15
    failed = schedule(card, AGAIN, NOW + timedelta(days=15), VN)
    assert (failed.status, failed.interval_days, failed.repetitions, failed.lapses) == ("learning", 0, 0, 1)
    assert failed.ease_factor == 2.3
    assert failed.next_review_at == NOW + timedelta(days=15, minutes=10)
    recovered = schedule(failed, GOOD, NOW + timedelta(days=15, minutes=11), VN)
    assert (recovered.status, recovered.interval_days, recovered.repetitions) == ("review", 1, 1)
    assert recovered.lapses == 1  # the lapse stays on record


def test_failing_a_new_or_learning_card_is_not_a_lapse():
    card = CardState()
    for _ in range(5):
        card = schedule(card, AGAIN, NOW, VN)
        assert card.lapses == 0
    assert card.status == "learning"


def test_a_card_at_one_day_that_is_forgotten_counts_as_a_lapse():
    card = schedule(CardState(), GOOD, NOW, VN)  # interval 1: it has been through review
    assert schedule(card, AGAIN, NOW, VN).lapses == 1


def test_ease_never_drops_below_the_floor():
    card = CardState()
    for _ in range(30):
        card = schedule(card, AGAIN, NOW, VN)
    assert card.ease_factor == EASE_MIN
    for _ in range(30):
        card = schedule(replace(card, interval_days=5, repetitions=3), HARD, NOW, VN)
    assert card.ease_factor == EASE_MIN


def test_ease_does_not_drift_in_float_arithmetic():
    card = CardState()
    for rating in (HARD, EASY, HARD, EASY, HARD, EASY):
        card = schedule(card, rating, NOW, VN)
    assert card.ease_factor == round(card.ease_factor, 2)


def test_the_interval_is_capped():
    huge = CardState(status="mastered", interval_days=MAX_INTERVAL_DAYS - 1, repetitions=50, first_reviewed_at=NOW)
    assert schedule(huge, EASY, NOW, VN).interval_days == MAX_INTERVAL_DAYS
    assert schedule(replace(huge, interval_days=MAX_INTERVAL_DAYS), GOOD, NOW, VN).interval_days == MAX_INTERVAL_DAYS


# dates -------------------------------------------------------------------------------------------------------


def test_reviews_are_due_from_the_start_of_a_local_day_whatever_the_time_of_day():
    for hour in (0, 6, 9, 23):
        now = datetime(2026, 10, 21, hour, 59, tzinfo=VN)
        card = schedule(CardState(), GOOD, now, VN)
        assert card.next_review_at == datetime(2026, 10, 22, tzinfo=VN)  # tomorrow 00:00 local, always


def test_a_morning_studier_sees_yesterdays_cards():
    """Reviewed at 09:05 with a one day interval, due again from midnight: visible at 09:00 next day."""
    reviewed = datetime(2026, 10, 21, 9, 5, tzinfo=VN)
    card = schedule(CardState(), GOOD, reviewed, VN)
    next_morning = datetime(2026, 10, 22, 9, 0, tzinfo=VN)
    assert card.next_review_at <= next_morning


def test_a_late_night_review_uses_the_users_day_not_utc():
    # 23:30 in Vietnam is 16:30 UTC the same day; 01:30 in Vietnam is 18:30 UTC the day before.
    late = schedule(CardState(), GOOD, datetime(2026, 10, 21, 16, 30, tzinfo=UTC), VN)
    early = schedule(CardState(), GOOD, datetime(2026, 10, 20, 18, 30, tzinfo=UTC), VN)
    assert late.next_review_at == datetime(2026, 10, 22, tzinfo=VN)  # local date 21st (+1)
    assert early.next_review_at == datetime(2026, 10, 22, tzinfo=VN)  # local date 21st too (+1)
    assert late.next_review_at.astimezone(UTC) == datetime(2026, 10, 21, 17, 0, tzinfo=UTC)


@pytest.mark.parametrize(
    "zone", ["America/Los_Angeles", "Europe/London", "Australia/Lord_Howe", "Pacific/Kiritimati", "Asia/Kolkata"]
)
def test_due_date_is_local_midnight_in_any_zone(zone):
    tz = ZoneInfo(zone)
    card = schedule(CardState(), GOOD, datetime(2026, 10, 21, 12, 0, tzinfo=UTC), tz)
    due = card.next_review_at.astimezone(tz)
    assert (due.hour, due.minute, due.second) == (0, 0, 0)
    assert due.date() == datetime(2026, 10, 21, 12, 0, tzinfo=UTC).astimezone(tz).date() + timedelta(days=1)


def test_daylight_saving_changes_do_not_move_the_due_date():
    tz = ZoneInfo("America/Los_Angeles")  # clocks go back on 2026-11-01
    before = datetime(2026, 10, 31, 20, 0, tzinfo=tz)
    due = schedule(CardState(), GOOD, before, tz).next_review_at
    assert due == datetime(2026, 11, 1, tzinfo=tz)  # the 25-hour day starts at its own midnight
    assert due.utcoffset() == timedelta(hours=-7)  # still PDT at midnight
    two_days = schedule(replace(CardState(), repetitions=1, interval_days=1), GOOD, before, tz).next_review_at
    assert two_days == datetime(2026, 11, 6, tzinfo=tz)  # 6 days: after the change, PST
    assert two_days.utcoffset() == timedelta(hours=-8)


def test_again_late_at_night_never_comes_back_after_hard():
    """Found by the property tests: at 23:55, +10 minutes (00:05) would be later than hard (00:00)."""
    late = datetime(2026, 10, 21, 23, 55, tzinfo=VN)
    again = schedule(CardState(), AGAIN, late, VN).next_review_at
    hard = schedule(CardState(), HARD, late, VN).next_review_at
    assert again == hard == datetime(2026, 10, 22, tzinfo=VN)
    assert schedule(CardState(), AGAIN, datetime(2026, 10, 21, 23, 49, tzinfo=VN), VN).next_review_at == datetime(
        2026, 10, 21, 23, 59, tzinfo=VN
    )  # well before midnight: the full ten minutes


def test_a_day_that_starts_at_a_skipped_hour_still_gives_a_valid_date():
    tz = ZoneInfo("America/Havana")  # clocks jump 00:00 -> 01:00 in spring
    card = schedule(CardState(), GOOD, datetime(2026, 3, 7, 12, 0, tzinfo=tz), tz)
    assert card.next_review_at.astimezone(tz).date().isoformat() == "2026-03-08"


# preview and inputs ----------------------------------------------------------------------------------------------


def test_preview_matches_what_answering_would_do():
    card = review(CardState(), GOOD, GOOD)
    shown = preview(card, NOW, VN)
    assert set(shown) == set(RATINGS)
    for rating, (days, due) in shown.items():
        after = schedule(card, rating, NOW, VN)
        assert (days, due) == (after.interval_days, after.next_review_at)
    assert shown[AGAIN][0] == 0 and shown[AGAIN][1] == NOW + timedelta(minutes=10)
    assert [shown[r][0] for r in RATINGS] == sorted(shown[r][0] for r in RATINGS)


def test_schedule_does_not_change_its_input_and_keeps_the_first_review_date():
    original = CardState()
    first = schedule(original, GOOD, NOW, VN)
    assert original == CardState()
    later = schedule(first, GOOD, NOW + timedelta(days=1), VN)
    assert later.first_reviewed_at == NOW
    assert later.last_reviewed_at == NOW + timedelta(days=1)


@pytest.mark.parametrize("rating", [0, 5, -1, 2.5, "3", None, True * 7])
def test_invalid_ratings_are_refused(rating):
    with pytest.raises(ValueError):
        schedule(CardState(), rating, NOW, VN)


def test_a_naive_time_is_refused():
    with pytest.raises(ValueError, match="timezone-aware"):
        schedule(CardState(), GOOD, datetime(2026, 10, 21, 8, 5), VN)


# properties over random review histories -----------------------------------------------------------------------------

zones = st.sampled_from(
    ["Asia/Ho_Chi_Minh", "UTC", "America/Los_Angeles", "Europe/Berlin", "Asia/Taipei", "Pacific/Auckland"]
)
histories = st.lists(st.sampled_from(RATINGS), min_size=0, max_size=40)
instants = st.datetimes(min_value=datetime(2024, 1, 1), max_value=datetime(2030, 1, 1)).map(
    lambda d: d.replace(tzinfo=UTC)
)


def replay(ratings, tz, start) -> CardState:
    card, now = CardState(), start
    for rating in ratings:
        card = schedule(card, rating, now, tz)
        now = card.next_review_at  # answer each card exactly when it falls due
    return card


@settings(max_examples=300, deadline=None)
@given(histories, zones, instants)
def test_a_history_always_leaves_a_valid_card(ratings, zone, start):
    tz = ZoneInfo(zone)
    card = replay(ratings, tz, start)
    if not ratings:
        assert card == CardState()
        return
    assert card.status in ("learning", "review", "mastered")  # never "new" again
    assert card.ease_factor >= EASE_MIN and card.ease_factor == round(card.ease_factor, 2)
    assert 0 <= card.interval_days <= MAX_INTERVAL_DAYS
    assert (card.status == "learning") == (card.interval_days == 0)
    assert (card.status == "mastered") == (card.interval_days >= 21)
    assert card.repetitions == 0 if ratings[-1] == AGAIN else card.repetitions >= 1
    assert card.lapses <= ratings.count(AGAIN)
    assert card.first_reviewed_at is not None and card.first_reviewed_at <= card.last_reviewed_at


@settings(max_examples=300, deadline=None)
@given(histories, zones, instants)
def test_the_four_answers_are_ordered_for_any_card(ratings, zone, start):
    tz = ZoneInfo(zone)
    card = replay(ratings, tz, start)
    after = {r: schedule(card, r, start, tz) for r in RATINGS}
    intervals = [after[r].interval_days for r in RATINGS]
    assert intervals[0] == 0
    assert intervals == sorted(intervals)  # again <= hard <= good <= easy
    assert after[EASY].interval_days > after[GOOD].interval_days or after[GOOD].interval_days == MAX_INTERVAL_DAYS
    assert after[GOOD].ease_factor == card.ease_factor
    assert after[EASY].ease_factor >= after[GOOD].ease_factor >= after[HARD].ease_factor >= after[AGAIN].ease_factor
    due = [after[r].next_review_at for r in RATINGS]
    assert due == sorted(due) and all(d > start for d in due)


@settings(max_examples=300, deadline=None)
@given(histories, st.sampled_from([HARD, GOOD, EASY]), zones, instants)
def test_a_pass_on_a_graduated_card_always_moves_it_forward(ratings, rating, zone, start):
    tz = ZoneInfo(zone)
    card = replay(ratings, tz, start)
    after = schedule(card, rating, start, tz)
    assert after.interval_days >= 1
    if card.interval_days >= 1 and card.repetitions >= 1 and card.interval_days < MAX_INTERVAL_DAYS:
        assert after.interval_days >= card.interval_days  # passing never shortens a card's interval
    local = after.next_review_at.astimezone(tz)
    assert (local.hour, local.minute, local.second) == (0, 0, 0)
    assert local.date() == start.astimezone(tz).date() + timedelta(days=after.interval_days)


@settings(max_examples=200, deadline=None)
@given(histories, zones, instants)
def test_lapses_count_exactly_the_failures_of_graduated_cards(ratings, zone, start):
    tz = ZoneInfo(zone)
    card, now, expected = CardState(), start, 0
    for rating in ratings:
        if rating == AGAIN and card.interval_days >= 1:
            expected += 1
        card = schedule(card, rating, now, tz)
        now = card.next_review_at
    assert card.lapses == expected
