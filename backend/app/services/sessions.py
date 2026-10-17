import secrets
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models import UserSession
from app.security import hash_token


async def create_session(db: AsyncSession, user_id: int, user_agent: str | None) -> str:
    """Insert a session row and return the raw token for the cookie. The caller commits."""
    token = secrets.token_urlsafe(32)
    db.add(
        UserSession(
            user_id=user_id,
            token_hash=hash_token(token),
            expires_at=datetime.now(UTC) + timedelta(days=get_settings().session_ttl_days),
            user_agent=(user_agent or "")[:256] or None,
        )
    )
    await db.flush()
    return token


async def delete_session(db: AsyncSession, token: str) -> None:
    await db.execute(delete(UserSession).where(UserSession.token_hash == hash_token(token)))


async def delete_all_sessions(db: AsyncSession, user_id: int) -> None:
    await db.execute(delete(UserSession).where(UserSession.user_id == user_id))
