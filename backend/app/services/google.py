"""Google ID token verification (Google Identity Services sends a JWT "credential").

google-auth checks signature, `iss`, `aud` (our client id) and `exp`. We then read the
claims we need. `sub` is the only stable identifier; email can change.
"""

import asyncio
from dataclasses import dataclass
from functools import cache
from typing import Annotated, Protocol

import cachecontrol
import requests
from fastapi import Depends
from google.auth.exceptions import GoogleAuthError
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token

from app.config import get_settings
from app.errors import AppError


@dataclass(frozen=True)
class GoogleClaims:
    sub: str
    email: str
    email_verified: bool
    name: str | None = None
    picture: str | None = None


class GoogleVerifier(Protocol):
    async def __call__(self, credential: str) -> GoogleClaims: ...


@cache
def _transport() -> google_requests.Request:
    # Google's signing certificates are cacheable; without this every login would fetch them.
    return google_requests.Request(session=cachecontrol.CacheControl(requests.Session()))


def _verify_sync(credential: str, client_id: str) -> dict:
    return id_token.verify_oauth2_token(credential, _transport(), audience=client_id)


async def verify_google_credential(credential: str) -> GoogleClaims:
    client_id = get_settings().google_client_id
    if not client_id:
        raise AppError(503, "google_not_configured", "Google sign-in is not configured.")
    try:
        claims = await asyncio.to_thread(_verify_sync, credential, client_id)
    except (ValueError, GoogleAuthError) as exc:
        raise AppError(401, "invalid_google_token", "Google sign-in could not be verified.") from exc

    sub, email = claims.get("sub"), claims.get("email")
    if not sub or not email:
        raise AppError(401, "invalid_google_token", "Google token has no subject or email.")
    # The claim is a boolean in current tokens and the string "true" in older ones.
    verified = claims.get("email_verified") in (True, "true")
    picture = claims.get("picture")
    return GoogleClaims(
        sub=str(sub),
        email=str(email),
        email_verified=verified,
        name=claims.get("name"),
        picture=picture if isinstance(picture, str) and picture.startswith("https://") else None,
    )


def get_google_verifier() -> GoogleVerifier:
    """FastAPI dependency; tests override it with a fake."""
    return verify_google_credential


GoogleVerifierDep = Annotated[GoogleVerifier, Depends(get_google_verifier)]
