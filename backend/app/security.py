"""Session cookie lookup and CSRF protection.

- `sid` cookie: random session token, httpOnly. Only sha256(token) is stored in `sessions`.
- `csrf_token` cookie: HMAC of the session token, readable by JS. Every unsafe request
  that carries a session must echo it in the X-CSRF-Token header (double submit, bound
  to the session so a cookie planted by a sibling subdomain cannot match).
"""

import hashlib
import hmac
from datetime import UTC, datetime
from typing import Annotated

from fastapi import Depends, Request, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db import get_db
from app.errors import AppError
from app.models import User, UserSession

SESSION_COOKIE = "sid"
CSRF_COOKIE = "csrf_token"
CSRF_HEADER = "X-CSRF-Token"
_SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


def hash_token(token: str) -> bytes:
    return hashlib.sha256(token.encode()).digest()


def csrf_token_for(session_token: str) -> str:
    key = get_settings().secret_key.get_secret_value().encode()
    return hmac.new(key, b"csrf:" + session_token.encode(), hashlib.sha256).hexdigest()


async def csrf_protect(request: Request) -> None:
    """App-wide dependency. Requests without a session have nothing to forge."""
    if request.method in _SAFE_METHODS:
        return
    session_token = request.cookies.get(SESSION_COOKIE)
    if not session_token:
        return
    sent = request.headers.get(CSRF_HEADER, "")
    if not hmac.compare_digest(sent, csrf_token_for(session_token)):
        raise AppError(403, "csrf_failed", "Missing or invalid CSRF token.")


def set_session_cookies(response: Response, session_token: str) -> None:
    settings = get_settings()
    max_age = settings.session_ttl_days * 86400
    common = {"max_age": max_age, "secure": settings.cookie_secure, "samesite": "lax", "path": "/"}
    response.set_cookie(SESSION_COOKIE, session_token, httponly=True, **common)
    response.set_cookie(CSRF_COOKIE, csrf_token_for(session_token), httponly=False, **common)


def clear_session_cookies(response: Response) -> None:
    response.delete_cookie(SESSION_COOKIE, path="/")
    response.delete_cookie(CSRF_COOKIE, path="/")


async def optional_user(request: Request, db: Annotated[AsyncSession, Depends(get_db)]) -> User | None:
    session_token = request.cookies.get(SESSION_COOKIE)
    if not session_token:
        return None
    return await db.scalar(
        select(User)
        .join(UserSession, UserSession.user_id == User.id)
        .where(UserSession.token_hash == hash_token(session_token), UserSession.expires_at > datetime.now(UTC))
    )


async def current_user(user: Annotated[User | None, Depends(optional_user)]) -> User:
    if user is None:
        raise AppError(401, "not_authenticated", "Sign in required.")
    return user
