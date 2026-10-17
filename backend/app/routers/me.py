from fastapi import APIRouter

from app.deps import CurrentUser, Db
from app.schemas.me import MeOut, MePatch

router = APIRouter(prefix="/me", tags=["me"])


@router.get("")
async def get_me(user: CurrentUser) -> MeOut:
    return MeOut.from_user(user)


@router.patch("")
async def patch_me(body: MePatch, user: CurrentUser, db: Db) -> MeOut:
    for name, value in body.model_dump(exclude_unset=True).items():
        setattr(user, name, value)
    await db.commit()
    await db.refresh(user)
    return MeOut.from_user(user)
