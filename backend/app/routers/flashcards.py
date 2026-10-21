from datetime import UTC
from typing import Annotated

from fastapi import APIRouter, Query

from app.deps import CurrentUser, Db, Now
from app.schemas.flashcards import CardOut, ExampleOut, NextOut, ReviewIn, ReviewOut, SessionOut, StatsOut
from app.schemas.me import Level
from app.services import flashcards, srs
from app.services.storage import audio_url

router = APIRouter(prefix="/flashcards", tags=["flashcards"])

BIGINT_MAX = 2**63 - 1


@router.get("/session")
async def session(
    user: CurrentUser,
    db: Db,
    now: Now,
    level: Level | None = None,
    group_id: Annotated[int | None, Query(ge=1, le=BIGINT_MAX)] = None,
    limit: Annotated[
        int, Query(ge=1, le=200, description="most reviews in the session")
    ] = flashcards.DEFAULT_SESSION_LIMIT,
) -> SessionOut:
    """The cards to study now: due reviews (most overdue first), then new cards up to what the daily cap
    still allows. Filter by level or word list."""
    data = await flashcards.build_session(db, user, now, level=level, group_id=group_id, limit=limit)

    def card(progress, vocab) -> CardOut:
        state = flashcards.to_state(progress)
        example = data.examples.get(vocab.id)
        return CardOut(
            vocabulary_id=vocab.id,
            traditional=vocab.traditional,
            simplified=vocab.simplified,
            pinyin=vocab.pinyin,
            zhuyin=vocab.zhuyin,
            part_of_speech=vocab.part_of_speech,
            level=vocab.level,
            audio_url=audio_url(vocab.audio_path),
            meanings=data.meanings[vocab.id],
            example=ExampleOut(
                hanzi=example.hanzi_text,
                pinyin=example.pinyin,
                zhuyin=example.zhuyin,
                translations=example.translations,
                audio_url=audio_url(example.audio_path),
            )
            if example
            else None,
            status=progress.status,
            is_new=progress.status == "new",
            interval_days=progress.interval_days,
            repetitions=progress.repetitions,
            next=[
                NextOut(rating=rating, interval_days=days, due_at=due.astimezone(UTC))
                for rating, (days, due) in srs.preview(state, now, data.tz).items()
            ],
        )

    return SessionOut(
        cards=[card(p, v) for p, v in data.reviews + data.new],
        due_total=data.due_total,
        new_waiting=data.new_waiting,
        new_allowance=data.new_allowance,
        new_today=data.new_today,
        daily_new_cards=user.daily_new_cards,
    )


@router.post("/review")
async def review(body: ReviewIn, user: CurrentUser, db: Db, now: Now) -> ReviewOut:
    """Answer a card: 1 again, 2 hard, 3 good, 4 easy. Updates its schedule and logs the review, in one
    transaction. A card in review that is not due yet is refused with 409 not_due."""
    progress = await flashcards.apply_review(db, user, body.vocabulary_id, body.rating, now)
    await db.commit()
    return ReviewOut(
        vocabulary_id=progress.vocabulary_id,
        status=progress.status,
        interval_days=progress.interval_days,
        repetitions=progress.repetitions,
        lapses=progress.lapses,
        ease_factor=round(float(progress.ease_factor), 2),
        next_review_at=progress.next_review_at,
    )


@router.get("/stats")
async def stats(user: CurrentUser, db: Db, now: Now) -> StatsOut:
    data = await flashcards.stats(db, user, now)
    return StatsOut(**vars(data))
