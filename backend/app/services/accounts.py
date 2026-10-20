"""Account rules that the database does not enforce (FEATURES.md rules 2, 3 and 4)."""

from datetime import UTC, datetime

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.errors import AppError
from app.models import User, UserIdentity
from app.schemas.me import MeOut
from app.services.google import GoogleClaims
from app.services.sessions import delete_all_sessions

UNIQUE_VIOLATION = "23505"


def is_unique_violation(exc: IntegrityError) -> bool:
    orig = exc.orig
    code = getattr(orig, "sqlstate", None) or getattr(getattr(orig, "__cause__", None), "sqlstate", None)
    return code == UNIQUE_VIOLATION


async def google_identity(db: AsyncSession, user_id: int) -> UserIdentity | None:
    return await db.scalar(
        select(UserIdentity).where(UserIdentity.user_id == user_id, UserIdentity.provider == "google")
    )


async def me_out(db: AsyncSession, user: User) -> MeOut:
    identity = await google_identity(db, user.id)
    return MeOut.from_user(user, has_password=user.password_hash is not None, google_linked=identity is not None)


async def _login_with_google_once(db: AsyncSession, claims: GoogleClaims) -> User:
    now = datetime.now(UTC)

    # Rule 3: the account is found by (provider, sub), never by email.
    identity = await db.scalar(
        select(UserIdentity).where(UserIdentity.provider == "google", UserIdentity.provider_user_id == claims.sub)
    )
    if identity is not None:
        identity.email = claims.email
        identity.last_login_at = now
        user = await db.get(User, identity.user_id)
        assert user is not None  # FK guarantees it
        return user

    user = await db.scalar(select(User).where(User.email == claims.email).with_for_update())

    if user is None:
        user = User(
            email=claims.email,
            email_verified_at=now if claims.email_verified else None,
            display_name=claims.name,
            avatar_url=claims.picture,
        )
        db.add(user)
        await db.flush()
    else:
        existing = await google_identity(db, user.id)
        if existing is not None:
            if existing.provider_user_id == claims.sub:
                # A concurrent first login for this same Google account committed after our
                # identity lookup above: the account exists now, so this is just a login.
                existing.email = claims.email
                existing.last_login_at = now
                return user
            raise AppError(
                409, "google_account_conflict", "This email belongs to an account linked to another Google account."
            )
        if not claims.email_verified:
            raise AppError(
                409,
                "google_email_unverified",
                "Google has not verified this email. Sign in with your password and link Google from your profile.",
            )
        if user.email_verified_at is None:
            # Pre-registration takeover defence: someone may have signed up with this address
            # (and chosen the password) without owning it. Google just proved the real owner
            # controls it, so drop that password and every session before linking.
            user.password_hash = None
            await delete_all_sessions(db, user.id)
            user.email_verified_at = now
        # else: Google and the local account both verified the address, so link without further proof.

    db.add(
        UserIdentity(
            user_id=user.id, provider="google", provider_user_id=claims.sub, email=claims.email, last_login_at=now
        )
    )
    await db.flush()
    return user


async def login_with_google(db: AsyncSession, claims: GoogleClaims) -> User:
    """Find, link or create the account for a verified Google identity.

    Rule 4: two simultaneous first logins race on the unique keys (identity and email). The
    loser's savepoint fails with a unique violation; we roll back to it and look again, which
    now finds what the winner committed.
    """
    for _ in range(3):
        try:
            async with db.begin_nested():
                return await _login_with_google_once(db, claims)
        except IntegrityError as exc:
            if not is_unique_violation(exc):
                raise
    raise AppError(409, "conflict", "Could not complete sign-in, please try again.")


async def link_google(db: AsyncSession, user: User, claims: GoogleClaims) -> None:
    """Attach a Google account to an already signed-in user."""
    if await google_identity(db, user.id) is not None:
        raise AppError(409, "google_already_linked", "A Google account is already linked.")
    try:
        async with db.begin_nested():
            db.add(
                UserIdentity(
                    user_id=user.id,
                    provider="google",
                    provider_user_id=claims.sub,
                    email=claims.email,
                    last_login_at=datetime.now(UTC),
                )
            )
            await db.flush()
    except IntegrityError as exc:
        if not is_unique_violation(exc):
            raise
        raise AppError(409, "google_account_in_use", "That Google account is linked to another user.") from exc
    if claims.email_verified and user.email_verified_at is None and claims.email.lower() == user.email.lower():
        user.email_verified_at = datetime.now(UTC)


async def unlink_google(db: AsyncSession, user: User) -> None:
    """Rule 2: never remove the last login method. The user row lock serialises this with
    anything else that changes the user's login methods."""
    locked = await db.scalar(
        select(User).where(User.id == user.id).with_for_update().execution_options(populate_existing=True)
    )
    assert locked is not None
    identity = await google_identity(db, user.id)
    if identity is None:
        raise AppError(404, "not_found", "No Google account is linked.")
    if locked.password_hash is None:
        raise AppError(409, "last_login_method", "Set a password before unlinking Google.")
    await db.delete(identity)


async def delete_user(db: AsyncSession, user: User) -> None:
    # ON DELETE CASCADE removes identities, sessions, tokens and all learning history.
    await db.execute(delete(User).where(User.id == user.id))
