from fastapi import APIRouter, Request, Response
from sqlalchemy.exc import IntegrityError

from app.deps import CurrentUser, Db
from app.errors import AppError
from app.schemas.me import ChangePasswordIn, DeleteAccountIn, MeOut, MePatch
from app.security import clear_session_cookies
from app.services import ratelimit
from app.services.accounts import delete_user, google_identity, is_unique_violation, me_out
from app.services.google import GoogleVerifierDep
from app.services.passwords import ahash_password, averify_password
from app.services.sessions import delete_all_sessions

from .auth import start_session

router = APIRouter(prefix="/me", tags=["me"])


@router.get("")
async def get_me(user: CurrentUser, db: Db) -> MeOut:
    return await me_out(db, user)


@router.patch("")
async def patch_me(body: MePatch, user: CurrentUser, db: Db) -> MeOut:
    changes = body.model_dump(exclude_unset=True)
    if "display_name" in changes and not changes["display_name"]:
        changes["display_name"] = None
    try:
        async with db.begin_nested():
            for name, value in changes.items():
                setattr(user, name, value)
            await db.flush()
    except IntegrityError as exc:
        if not is_unique_violation(exc):
            raise
        raise AppError(409, "username_taken", "That username is already taken.") from exc
    await db.commit()
    await db.refresh(user)
    return await me_out(db, user)


@router.put("/password")
async def change_password(
    body: ChangePasswordIn, request: Request, response: Response, user: CurrentUser, db: Db
) -> MeOut:
    if user.password_hash is not None:
        email = user.email.lower()
        ratelimit.login_by_email.check(email)
        if not body.current_password or not await averify_password(user.password_hash, body.current_password):
            ratelimit.login_by_email.record(email)
            raise AppError(401, "invalid_credentials", "Current password is wrong.")
    user.password_hash = await ahash_password(body.new_password)
    # Sign out every device, including any that held the old password, and keep this one.
    await delete_all_sessions(db, user.id)
    await start_session(db, user, request, response)
    return await me_out(db, user)


@router.delete("", status_code=204)
async def delete_account(
    body: DeleteAccountIn, response: Response, user: CurrentUser, db: Db, verifier: GoogleVerifierDep
) -> None:
    """Re-authenticates first: a stolen session alone must not be able to wipe an account."""
    if user.password_hash is not None:
        email = user.email.lower()
        ratelimit.login_by_email.check(email)
        if not body.password or not await averify_password(user.password_hash, body.password):
            ratelimit.login_by_email.record(email)
            raise AppError(401, "invalid_credentials", "Wrong password.")
    else:
        identity = await google_identity(db, user.id)
        if not body.credential or identity is None:
            raise AppError(401, "reauth_required", "Confirm with your Google account to delete.")
        claims = await verifier(body.credential)
        if claims.sub != identity.provider_user_id:
            raise AppError(401, "invalid_google_token", "That Google account does not match.")
    await delete_user(db, user)
    await db.commit()
    clear_session_cookies(response)
