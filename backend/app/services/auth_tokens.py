"""Single-use emailed tokens. The raw token goes into the email; only sha256 is stored."""

import secrets
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuthToken, User
from app.security import hash_token


async def create_token(db: AsyncSession, user: User, purpose: str, ttl: timedelta) -> str:
    """Issue a token for the user's current email, replacing any unused one of the same purpose."""
    await db.execute(
        delete(AuthToken).where(AuthToken.user_id == user.id, AuthToken.purpose == purpose, AuthToken.used_at.is_(None))
    )
    raw = secrets.token_urlsafe(32)
    now = datetime.now(UTC)
    db.add(
        AuthToken(
            user_id=user.id,
            purpose=purpose,
            token_hash=hash_token(raw),
            email=user.email,
            created_at=now,
            expires_at=now + ttl,
        )
    )
    await db.flush()
    return raw


async def consume_token(db: AsyncSession, raw: str, purpose: str) -> AuthToken | None:
    """Mark a valid token used and return it; None if unknown, used, expired or of another purpose.
    The row lock makes two simultaneous clicks consume it once."""
    token = await db.scalar(
        select(AuthToken)
        .where(
            AuthToken.token_hash == hash_token(raw),
            AuthToken.purpose == purpose,
            AuthToken.used_at.is_(None),
            AuthToken.expires_at > datetime.now(UTC),
        )
        .with_for_update()
    )
    if token is not None:
        token.used_at = datetime.now(UTC)
    return token
