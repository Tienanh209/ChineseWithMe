import re
from datetime import UTC, datetime, timedelta

from httpx import AsyncClient
from sqlalchemy import select, update

from app.models import AuthToken, User, UserSession
from app.security import hash_token
from app.services import mailer
from tests.conftest import use_csrf

NEW = {"email": "new.user@example.com", "password": "correct horse battery"}


def token_from_mail(mail: mailer.Mail) -> str:
    return re.search(r"token=([\w-]+)", mail.body).group(1)


def other_client(client: AsyncClient) -> AsyncClient:
    return AsyncClient(transport=client._transport, base_url="http://test")


async def get_user(db, email) -> User | None:
    return await db.scalar(select(User).where(User.email == email).execution_options(populate_existing=True))


# registration ---------------------------------------------------------------


async def test_register_creates_account_session_and_verification_mail(client, db):
    response = await client.post(
        "/api/auth/register", json={**NEW, "display_name": " New ", "ui_lang": "en", "target_level": "B1"}
    )
    assert response.status_code == 201
    body = response.json()
    assert body["email"] == NEW["email"]
    assert (body["display_name"], body["ui_lang"], body["target_level"]) == ("New", "en", "B1")
    assert body["email_verified"] is False and body["has_password"] is True and body["role"] == "user"

    cookies = response.headers.get_list("set-cookie")
    assert any(c.startswith("sid=") and "HttpOnly" in c for c in cookies)
    use_csrf(client)
    assert (await client.get("/api/me")).status_code == 200  # already signed in

    user = await get_user(db, NEW["email"])
    assert user.password_hash.startswith("$argon2id$")
    assert len(mailer.outbox) == 1
    mail = mailer.outbox[0]
    assert mail.to == NEW["email"]
    assert "http://test/verify-email?token=" in mail.body
    assert "Confirm your email" in mail.subject  # the ui_lang sent at sign-up
    # only the hash is stored
    stored = await db.scalar(select(AuthToken).where(AuthToken.user_id == user.id))
    assert stored.token_hash == hash_token(token_from_mail(mail))
    assert token_from_mail(mail) not in repr(stored.__dict__)


async def test_register_rejects_duplicate_email_ignoring_case(client, seeded):
    response = await client.post("/api/auth/register", json={**NEW, "email": "TEST@example.com"})
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "email_taken"


async def test_register_validation(client):
    for body in (
        {**NEW, "email": "not-an-email"},
        {**NEW, "password": "short"},
        {**NEW, "password": "x" * 129},
        {**NEW, "ui_lang": "fr"},
        {**NEW, "role": "admin"},
        {"email": NEW["email"]},
    ):
        assert (await client.post("/api/auth/register", json=body)).status_code == 422, body


async def test_register_is_rate_limited_per_ip(client):
    for i in range(10):
        response = await client.post("/api/auth/register", json={**NEW, "email": f"u{i}@example.com"})
        assert response.status_code == 201
        client.cookies.clear()
    blocked = await client.post("/api/auth/register", json={**NEW, "email": "u11@example.com"})
    assert blocked.status_code == 429
    assert blocked.json()["error"]["code"] == "rate_limited"
    assert int(blocked.headers["Retry-After"]) > 0


# login / logout -------------------------------------------------------------


async def test_login_logout_roundtrip(client, seeded):
    ok = await client.post("/api/auth/login", json={"email": "TEST@example.com", "password": "password123"})
    assert ok.status_code == 200 and ok.json()["email"] == "test@example.com"
    use_csrf(client)
    assert (await client.get("/api/me")).status_code == 200
    assert (await client.post("/api/auth/logout")).status_code == 204
    assert (await client.get("/api/me")).status_code == 401


async def test_logout_deletes_only_this_session(client, seeded, db):
    other = other_client(client)
    async with other:
        await other.post("/api/auth/login", json={"email": "test@example.com", "password": "password123"})
        await client.post("/api/auth/login", json={"email": "test@example.com", "password": "password123"})
        use_csrf(client)
        await client.post("/api/auth/logout")
        assert (await other.get("/api/me")).status_code == 200


async def test_wrong_password_and_unknown_email_look_the_same(client, seeded):
    wrong = await client.post("/api/auth/login", json={"email": "test@example.com", "password": "nope-nope"})
    unknown = await client.post("/api/auth/login", json={"email": "nobody@example.com", "password": "nope-nope"})
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json()["error"]["code"] == unknown.json()["error"]["code"] == "invalid_credentials"
    assert wrong.json()["error"]["message"] == unknown.json()["error"]["message"]


async def test_login_locks_out_an_email_after_five_failures_but_not_other_emails(client, seeded):
    for _ in range(5):
        r = await client.post("/api/auth/login", json={"email": "test@example.com", "password": "wrong-pass"})
        assert r.status_code == 401
    locked = await client.post("/api/auth/login", json={"email": "test@example.com", "password": "password123"})
    assert locked.status_code == 429  # even the right password waits
    assert "Retry-After" in locked.headers
    admin = await client.post("/api/auth/login", json={"email": "admin@example.com", "password": "password123"})
    assert admin.status_code == 200


async def test_login_limits_per_ip_across_emails(client, seeded):
    for i in range(20):
        await client.post("/api/auth/login", json={"email": f"x{i}@example.com", "password": "wrong-pass"})
    blocked = await client.post("/api/auth/login", json={"email": "test@example.com", "password": "password123"})
    assert blocked.status_code == 429


async def test_successful_login_resets_the_email_counter(client, seeded):
    for _ in range(4):
        await client.post("/api/auth/login", json={"email": "test@example.com", "password": "wrong-pass"})
    assert (
        await client.post("/api/auth/login", json={"email": "test@example.com", "password": "password123"})
    ).status_code == 200
    client.cookies.clear()
    for _ in range(4):
        r = await client.post("/api/auth/login", json={"email": "test@example.com", "password": "wrong-pass"})
        assert r.status_code == 401


async def test_google_only_account_cannot_log_in_with_a_password(client, google):
    await client.post("/api/auth/google", json={"credential": google.token("sub-1", "g@example.com")})
    client.cookies.clear()
    response = await client.post("/api/auth/login", json={"email": "g@example.com", "password": "anything-at-all"})
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "invalid_credentials"


async def test_session_cookie_is_an_opaque_random_token_stored_hashed(client, seeded, db):
    response = await client.post("/api/auth/login", json={"email": "test@example.com", "password": "password123"})
    sid = client.cookies["sid"]
    assert len(sid) >= 40
    session = await db.scalar(select(UserSession))
    assert session.token_hash == hash_token(sid)
    assert response.json()["id"] == session.user_id


async def test_expired_session_is_not_accepted(user_client, db):
    await db.execute(
        update(UserSession).values(
            expires_at=datetime.now(UTC) - timedelta(seconds=1), created_at=datetime.now(UTC) - timedelta(days=2)
        )
    )
    assert (await user_client.get("/api/me")).status_code == 401


# email verification ---------------------------------------------------------


async def test_verify_email_flow(client, db):
    await client.post("/api/auth/register", json=NEW)
    token = token_from_mail(mailer.outbox[0])
    assert (await get_user(db, NEW["email"])).email_verified_at is None

    # no session needed (the link may open in another browser)
    fresh = other_client(client)
    async with fresh:
        assert (await fresh.post("/api/auth/verify-email", json={"token": token})).status_code == 204
    assert (await get_user(db, NEW["email"])).email_verified_at is not None

    use_csrf(client)
    again = await client.post("/api/auth/verify-email", json={"token": token})
    assert again.status_code == 400  # single use
    assert again.json()["error"]["code"] == "invalid_token"


async def test_verify_email_rejects_unknown_expired_and_stale_tokens(client, db):
    await client.post("/api/auth/register", json=NEW)
    use_csrf(client)
    token = token_from_mail(mailer.outbox[0])

    assert (await client.post("/api/auth/verify-email", json={"token": "nope"})).status_code == 400

    # a token is only good for the address it was sent to
    await db.execute(update(User).where(User.email == NEW["email"]).values(email="changed@example.com"))
    assert (await client.post("/api/auth/verify-email", json={"token": token})).status_code == 400
    await db.execute(update(User).where(User.email == "changed@example.com").values(email=NEW["email"]))

    await db.execute(
        update(AuthToken).values(
            created_at=datetime.now(UTC) - timedelta(days=3), expires_at=datetime.now(UTC) - timedelta(days=1)
        )
    )
    assert (await client.post("/api/auth/verify-email", json={"token": token})).status_code == 400
    assert (await get_user(db, NEW["email"])).email_verified_at is None


async def test_resend_verification_replaces_the_old_link(client, db):
    await client.post("/api/auth/register", json=NEW)
    use_csrf(client)
    first = token_from_mail(mailer.outbox[0])
    assert (await client.post("/api/auth/resend-verification")).status_code == 204
    second = token_from_mail(mailer.outbox[1])
    assert first != second
    assert (await client.post("/api/auth/verify-email", json={"token": first})).status_code == 400
    assert (await client.post("/api/auth/verify-email", json={"token": second})).status_code == 204
    assert (await client.post("/api/auth/resend-verification")).status_code == 409  # already verified


async def test_resend_verification_is_rate_limited_per_address(client):
    await client.post("/api/auth/register", json=NEW)
    use_csrf(client)
    codes = [(await client.post("/api/auth/resend-verification")).status_code for _ in range(4)]
    assert codes == [204, 204, 204, 429]


# password reset -------------------------------------------------------------


async def test_forgot_password_does_not_reveal_whether_the_account_exists(client, seeded):
    known = await client.post("/api/auth/forgot-password", json={"email": "test@example.com"})
    unknown = await client.post("/api/auth/forgot-password", json={"email": "nobody@example.com"})
    assert known.status_code == unknown.status_code == 204
    assert [m.to for m in mailer.outbox] == ["test@example.com"]
    assert "http://test/reset-password?token=" in mailer.outbox[0].body


async def test_reset_password_sets_password_signs_out_everywhere_and_verifies_email(client, db):
    await client.post("/api/auth/register", json=NEW)  # attacker-style: unverified, session open
    use_csrf(client)
    await client.post("/api/auth/forgot-password", json={"email": NEW["email"]})
    token = token_from_mail(mailer.outbox[-1])

    fresh = other_client(client)
    async with fresh:
        reset = await fresh.post("/api/auth/reset-password", json={"token": token, "password": "brand new password"})
        assert reset.status_code == 204
        assert (await fresh.post("/api/auth/login", json={**NEW})).status_code == 401
        assert (
            await fresh.post("/api/auth/login", json={"email": NEW["email"], "password": "brand new password"})
        ).status_code == 200
    assert (await client.get("/api/me")).status_code == 401  # old session is gone
    assert (await get_user(db, NEW["email"])).email_verified_at is not None

    again = await client.post("/api/auth/reset-password", json={"token": token, "password": "another password!"})
    assert again.status_code == 400


async def test_reset_token_cannot_verify_email_and_vice_versa(client):
    await client.post("/api/auth/register", json=NEW)
    use_csrf(client)
    verify_token = token_from_mail(mailer.outbox[0])
    await client.post("/api/auth/forgot-password", json={"email": NEW["email"]})
    reset_token = token_from_mail(mailer.outbox[1])
    assert (await client.post("/api/auth/verify-email", json={"token": reset_token})).status_code == 400
    assert (
        await client.post("/api/auth/reset-password", json={"token": verify_token, "password": "whatever-it-is"})
    ).status_code == 400


async def test_reset_password_validates_the_new_password(client, seeded):
    await client.post("/api/auth/forgot-password", json={"email": "test@example.com"})
    token = token_from_mail(mailer.outbox[0])
    assert (
        await client.post("/api/auth/reset-password", json={"token": token, "password": "short"})
    ).status_code == 422
    # a validation failure must not burn the token
    assert (
        await client.post("/api/auth/reset-password", json={"token": token, "password": "long enough now"})
    ).status_code == 204


async def test_mail_failure_does_not_fail_the_request(client, monkeypatch):
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "mail_backend", "smtp")
    monkeypatch.setattr(get_settings(), "smtp_port", 1)  # nothing listens here
    response = await client.post("/api/auth/register", json=NEW)
    assert response.status_code == 201


# csrf -----------------------------------------------------------------------


async def test_state_changing_auth_calls_need_csrf_once_signed_in(client, seeded):
    await client.post("/api/auth/login", json={"email": "test@example.com", "password": "password123"})
    # signed in (sid cookie present) but no X-CSRF-Token header
    response = await client.post("/api/auth/logout")
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "csrf_failed"
