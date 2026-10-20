from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, BackgroundTasks, Request, Response
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.config import get_settings
from app.deps import CurrentUser, Db
from app.errors import AppError
from app.models import User
from app.schemas.auth import (
    AuthConfig,
    ForgotPasswordIn,
    GoogleIn,
    GoogleLinkIn,
    LoginIn,
    RegisterIn,
    ResetPasswordIn,
    TokenIn,
)
from app.schemas.me import MeOut
from app.security import SESSION_COOKIE, clear_session_cookies, set_session_cookies
from app.services import ratelimit
from app.services.accounts import is_unique_violation, link_google, login_with_google, me_out, unlink_google
from app.services.auth_tokens import consume_token, create_token
from app.services.emails import reset_password_mail, verify_email_mail
from app.services.google import GoogleVerifierDep
from app.services.mailer import send_mail
from app.services.passwords import ahash_password, averify_password, dummy_hash, needs_rehash
from app.services.sessions import create_session, delete_all_sessions, delete_session

router = APIRouter(prefix="/auth", tags=["auth"])


def client_ip(request: Request) -> str:
    # Behind nginx uvicorn rewrites request.client from X-Forwarded-For (--proxy-headers).
    return request.client.host if request.client else "unknown"


async def start_session(db, user: User, request: Request, response: Response) -> None:
    token = await create_session(db, user.id, request.headers.get("user-agent"))
    await db.commit()
    set_session_cookies(response, token)


@router.get("/config")
async def auth_config() -> AuthConfig:
    return AuthConfig(google_client_id=get_settings().google_client_id or None)


@router.post("/register", status_code=201)
async def register(
    body: RegisterIn, request: Request, response: Response, db: Db, background: BackgroundTasks
) -> MeOut:
    ratelimit.register_by_ip.hit(client_ip(request))
    taken = AppError(409, "email_taken", "An account with this email already exists.")
    if await db.scalar(select(User.id).where(User.email == body.email)) is not None:
        raise taken

    extra = {k: v for k, v in (("ui_lang", body.ui_lang), ("target_level", body.target_level)) if v is not None}
    user = User(
        email=body.email, password_hash=await ahash_password(body.password), display_name=body.display_name, **extra
    )
    try:
        async with db.begin_nested():
            db.add(user)
            await db.flush()
    except IntegrityError as exc:  # lost a race with the same email
        if not is_unique_violation(exc):
            raise
        raise taken from exc

    token = await create_token(db, user, "verify_email", timedelta(hours=get_settings().verify_token_ttl_hours))
    await start_session(db, user, request, response)
    background.add_task(send_mail, verify_email_mail(user.email, user.ui_lang, token))
    return await me_out(db, user)


@router.post("/login")
async def login(body: LoginIn, request: Request, response: Response, db: Db) -> MeOut:
    ip, email = client_ip(request), body.email.lower()
    ratelimit.login_by_ip.check(ip)
    ratelimit.login_by_email.check(email)

    user = await db.scalar(select(User).where(User.email == body.email))
    stored = user.password_hash if user is not None else None
    # Always run one argon2 verification so timing does not reveal whether the account exists.
    valid = await averify_password(stored or dummy_hash(), body.password)
    if user is None or stored is None or not valid:
        ratelimit.login_by_ip.record(ip)
        ratelimit.login_by_email.record(email)
        raise AppError(401, "invalid_credentials", "Wrong email or password.")

    ratelimit.login_by_email.reset(email)
    if needs_rehash(stored):
        user.password_hash = await ahash_password(body.password)
    await start_session(db, user, request, response)
    return await me_out(db, user)


@router.post("/logout", status_code=204)
async def logout(request: Request, response: Response, db: Db) -> None:
    token = request.cookies.get(SESSION_COOKIE)
    if token:
        await delete_session(db, token)
        await db.commit()
    clear_session_cookies(response)


@router.post("/google")
async def google_login(
    body: GoogleIn, request: Request, response: Response, db: Db, verifier: GoogleVerifierDep
) -> MeOut:
    ip = client_ip(request)
    ratelimit.google_failures_by_ip.check(ip)
    try:
        claims = await verifier(body.credential)
    except AppError:
        ratelimit.google_failures_by_ip.record(ip)
        raise
    user = await login_with_google(db, claims)
    await start_session(db, user, request, response)
    return await me_out(db, user)


@router.post("/google/link")
async def google_link(body: GoogleLinkIn, user: CurrentUser, db: Db, verifier: GoogleVerifierDep) -> MeOut:
    if user.password_hash is not None:
        email = user.email.lower()
        ratelimit.login_by_email.check(email)
        if not body.password or not await averify_password(user.password_hash, body.password):
            ratelimit.login_by_email.record(email)
            raise AppError(401, "invalid_credentials", "Wrong password.")
    claims = await verifier(body.credential)
    await link_google(db, user, claims)
    await db.commit()
    return await me_out(db, user)


@router.delete("/google", status_code=204)
async def google_unlink(user: CurrentUser, db: Db) -> None:
    await unlink_google(db, user)
    await db.commit()


@router.post("/verify-email", status_code=204)
async def verify_email(body: TokenIn, db: Db) -> None:
    token = await consume_token(db, body.token, "verify_email")
    user = await db.get(User, token.user_id, with_for_update=True) if token else None
    # A token only counts for the address it was sent to.
    if token is None or user is None or user.email.lower() != token.email.lower():
        raise AppError(400, "invalid_token", "This link is invalid or has expired.")
    if user.email_verified_at is None:
        user.email_verified_at = datetime.now(UTC)
    await db.commit()


@router.post("/resend-verification", status_code=204)
async def resend_verification(request: Request, user: CurrentUser, db: Db, background: BackgroundTasks) -> None:
    if user.email_verified_at is not None:
        raise AppError(409, "already_verified", "Email is already verified.")
    ratelimit.email_by_ip.hit(client_ip(request))
    ratelimit.email_by_address.hit(user.email.lower())
    token = await create_token(db, user, "verify_email", timedelta(hours=get_settings().verify_token_ttl_hours))
    await db.commit()
    background.add_task(send_mail, verify_email_mail(user.email, user.ui_lang, token))


@router.post("/forgot-password", status_code=204)
async def forgot_password(body: ForgotPasswordIn, request: Request, db: Db, background: BackgroundTasks) -> None:
    """Always 204, so the response does not reveal whether the address has an account."""
    ratelimit.email_by_ip.hit(client_ip(request))
    ratelimit.email_by_address.hit(body.email.lower())
    user = await db.scalar(select(User).where(User.email == body.email))
    if user is None:
        return
    token = await create_token(db, user, "reset_password", timedelta(minutes=get_settings().reset_token_ttl_minutes))
    await db.commit()
    background.add_task(send_mail, reset_password_mail(user.email, user.ui_lang, token))


@router.post("/reset-password", status_code=204)
async def reset_password(body: ResetPasswordIn, db: Db) -> None:
    token = await consume_token(db, body.token, "reset_password")
    user = await db.get(User, token.user_id, with_for_update=True) if token else None
    if token is None or user is None or user.email.lower() != token.email.lower():
        raise AppError(400, "invalid_token", "This link is invalid or has expired.")
    user.password_hash = await ahash_password(body.password)
    if user.email_verified_at is None:
        user.email_verified_at = datetime.now(UTC)  # the link proved control of the address
    await delete_all_sessions(db, user.id)  # signs out whoever held the old password
    await db.commit()
