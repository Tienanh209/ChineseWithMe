from typing import Annotated

from fastapi import APIRouter, Path
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.deps import CurrentUser, Db
from app.errors import AppError
from app.models import UserVocabProgress, Vocabulary
from app.schemas.vocab import StudyAddOut

router = APIRouter(prefix="/study-list", tags=["study list"])


@router.post("/{vocab_id}")
async def add_to_study_list(
    vocab_id: Annotated[int, Path(ge=1, le=2**63 - 1)], user: CurrentUser, db: Db
) -> StudyAddOut:
    """Add a word to the user's study list: status 'new', due now. Adding a word that is already
    there changes nothing, so review progress is never reset by a second tap."""
    if await db.scalar(select(Vocabulary.id).where(Vocabulary.id == vocab_id)) is None:
        raise AppError(404, "not_found", "No such word.")
    inserted = await db.execute(
        pg_insert(UserVocabProgress)
        .values(user_id=user.id, vocabulary_id=vocab_id, status="new", next_review_at=func.now())
        .on_conflict_do_nothing()
    )
    progress = await db.scalar(
        select(UserVocabProgress)
        .where(UserVocabProgress.user_id == user.id, UserVocabProgress.vocabulary_id == vocab_id)
        .execution_options(populate_existing=True)
    )
    await db.commit()
    assert progress is not None
    return StudyAddOut(status=progress.status, next_review_at=progress.next_review_at, added=inserted.rowcount == 1)
