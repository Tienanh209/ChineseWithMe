"""Development-only sign-in, mounted only when ENV=dev. Replaced by real auth in M1."""

from fastapi import APIRouter, Request, Response
from pydantic import BaseModel
from sqlalchemy import select

from app.deps import Db
from app.errors import AppError
from app.models import User
from app.schemas.me import MeOut
from app.security import SESSION_COOKIE, clear_session_cookies, set_session_cookies
from app.services.sessions import create_session, delete_session

router = APIRouter(prefix="/dev", tags=["dev"])


class DevLogin(BaseModel):
    email: str


@router.post("/login")
async def dev_login(body: DevLogin, request: Request, response: Response, db: Db) -> MeOut:
    user = await db.scalar(select(User).where(User.email == body.email))
    if user is None:
        raise AppError(404, "not_found", "No user with that email. Run the seed first.")
    token = await create_session(db, user.id, request.headers.get("user-agent"))
    await db.commit()
    set_session_cookies(response, token)
    return MeOut.from_user(user)


@router.post("/logout", status_code=204)
async def dev_logout(request: Request, response: Response, db: Db) -> None:
    token = request.cookies.get(SESSION_COOKIE)
    if token:
        await delete_session(db, token)
        await db.commit()
    clear_session_cookies(response)
