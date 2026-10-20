"""Google sign-in rules (FEATURES.md rules 2, 3, 4) with a fake token verifier.
Signature, issuer, audience and expiry checks are covered in test_google_verifier.py."""

import asyncio

import pytest
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.models import User, UserIdentity, UserSession
from app.services.accounts import login_with_google
from app.services.google import GoogleClaims
from tests.conftest import use_csrf

REG = {"email": "victim@example.com", "password": "attacker chose this"}


async def count(db, model, *where) -> int:
    return await db.scalar(select(func.count()).select_from(model).where(*where))


async def user_by_email(db, email) -> User | None:
    return await db.scalar(select(User).where(User.email == email).execution_options(populate_existing=True))


async def identity_for(db, sub) -> UserIdentity | None:
    return await db.scalar(
        select(UserIdentity).where(UserIdentity.provider_user_id == sub).execution_options(populate_existing=True)
    )


async def google_login(client, google, sub, email, **kw):
    return await client.post("/api/auth/google", json={"credential": google.token(sub, email, **kw)})


# first login, returning login ------------------------------------------------


async def test_first_login_creates_user_and_identity(client, google, db):
    response = await google_login(client, google, "sub-1", "g.user@example.com", name="G User")
    assert response.status_code == 200
    body = response.json()
    assert body["email"] == "g.user@example.com"
    assert body["email_verified"] is True
    assert body["display_name"] == "G User"
    assert body["avatar_url"] == "https://lh3.example.com/p.png"
    assert body["username"] is None
    assert body["has_password"] is False and body["google_linked"] is True

    user = await user_by_email(db, "g.user@example.com")
    assert user.password_hash is None and user.username is None and user.email_verified_at is not None
    identity = await identity_for(db, "sub-1")
    assert (identity.user_id, identity.provider, identity.email) == (user.id, "google", "g.user@example.com")
    assert identity.last_login_at is not None

    use_csrf(client)
    assert (await client.get("/api/me")).json()["email"] == "g.user@example.com"  # session works


async def test_second_login_reuses_the_same_user(client, google, db):
    first = await google_login(client, google, "sub-1", "g.user@example.com")
    client.cookies.clear()
    second = await google_login(client, google, "sub-1", "g.user@example.com")
    assert first.json()["id"] == second.json()["id"]
    assert await count(db, User) == 1
    assert await count(db, UserIdentity) == 1


async def test_login_matches_on_sub_not_email(client, google, db):
    first = await google_login(client, google, "sub-1", "old@example.com")
    client.cookies.clear()
    # same Google account, address changed on Google's side
    second = await google_login(client, google, "sub-1", "renamed@example.com")
    assert second.json()["id"] == first.json()["id"]
    assert second.json()["email"] == "old@example.com"  # our email is not rewritten
    assert (await identity_for(db, "sub-1")).email == "renamed@example.com"
    assert await count(db, User) == 1


async def test_unverified_google_email_creates_unverified_account(client, google):
    response = await google_login(client, google, "sub-1", "new@example.com", verified=False)
    assert response.status_code == 200
    assert response.json()["email_verified"] is False


# linking to an existing local account ---------------------------------------


async def test_verified_both_sides_links_and_keeps_the_password(client, google, seeded, db):
    response = await google_login(client, google, "sub-t", "TEST@example.com")
    assert response.status_code == 200
    user = await user_by_email(db, "test@example.com")
    assert response.json()["id"] == user.id
    assert user.password_hash is not None
    assert (await identity_for(db, "sub-t")).user_id == user.id
    assert await count(db, User) == 2  # seed test + admin, no duplicate


async def test_unverified_local_account_is_taken_over_not_trusted(client, google, db):
    """Pre-registration attack: the attacker signs up with the victim's address and keeps a session."""
    await client.post("/api/auth/register", json=REG)
    use_csrf(client)
    assert (await client.get("/api/me")).status_code == 200  # attacker is in
    attacker_session_cookies = dict(client.cookies)

    victim = type(client)(transport=client._transport, base_url="http://test")
    async with victim:
        response = await google_login(victim, google, "sub-victim", REG["email"])
        assert response.status_code == 200
        assert response.json()["email_verified"] is True

        user = await user_by_email(db, REG["email"])
        assert user.password_hash is None  # attacker's password is gone
        assert await count(db, UserSession, UserSession.user_id == user.id) == 1  # only the victim's

        client.cookies.clear()
        for name, value in attacker_session_cookies.items():
            client.cookies.set(name, value)
        assert (await client.get("/api/me")).status_code == 401  # attacker's session is dead
        client.cookies.clear()
        login = await client.post("/api/auth/login", json=REG)
        assert login.status_code == 401  # and so is the password


async def test_unverified_google_email_never_links_to_an_existing_account(client, google, seeded, db):
    response = await google_login(client, google, "sub-t", "test@example.com", verified=False)
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "google_email_unverified"
    assert await identity_for(db, "sub-t") is None
    assert (await user_by_email(db, "test@example.com")).password_hash is not None  # untouched


async def test_unverified_google_email_does_not_take_over_an_unverified_local_account(client, google, db):
    await client.post("/api/auth/register", json=REG)
    client.cookies.clear()
    response = await google_login(client, google, "sub-x", REG["email"], verified=False)
    assert response.status_code == 409
    assert (await user_by_email(db, REG["email"])).password_hash is not None


async def test_account_linked_to_another_google_account_is_not_hijacked(client, google, seeded, db):
    assert (await google_login(client, google, "sub-first", "test@example.com")).status_code == 200
    client.cookies.clear()
    response = await google_login(client, google, "sub-second", "test@example.com")
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "google_account_conflict"
    assert await identity_for(db, "sub-second") is None


async def test_invalid_google_token_is_rejected_and_rate_limited(client, google):
    for _ in range(20):
        response = await client.post("/api/auth/google", json={"credential": "forged"})
        assert response.status_code == 401
        assert response.json()["error"]["code"] == "invalid_google_token"
    assert (await client.post("/api/auth/google", json={"credential": "forged"})).status_code == 429


# race: simultaneous first logins (rule 4) -------------------------------------


@pytest.fixture
async def committing_sessions(engine):
    """Two real, independent, committing sessions on a throwaway user; cleaned up afterwards."""
    factory = async_sessionmaker(engine, expire_on_commit=False)
    yield factory
    async with factory() as cleanup:
        await cleanup.execute(delete(User).where(User.email.like("race-%@example.com")))
        await cleanup.commit()


async def test_simultaneous_first_logins_create_exactly_one_user_deterministic(committing_sessions):
    """A has inserted but not committed; B starts and blocks on the unique key; when A commits,
    B's insert fails, it retries, and finds A's identity."""
    claims = GoogleClaims(sub="race-sub-1", email="race-1@example.com", email_verified=True, name="Racer")
    async with committing_sessions() as a, committing_sessions() as b:
        user_a = await login_with_google(a, claims)  # flushed, not committed

        async def second() -> User:
            user = await login_with_google(b, claims)
            await b.commit()
            return user

        task_b = asyncio.create_task(second())
        await asyncio.sleep(0.5)
        assert not task_b.done(), "B should be waiting on A's uncommitted row"
        await a.commit()
        user_b = await asyncio.wait_for(task_b, timeout=10)

    assert user_a.id == user_b.id
    async with committing_sessions() as check:
        assert await count(check, User, User.email == "race-1@example.com") == 1
        assert await count(check, UserIdentity, UserIdentity.provider_user_id == "race-sub-1") == 1


async def test_simultaneous_first_logins_via_gather(committing_sessions):
    for i in range(5):
        claims = GoogleClaims(sub=f"race-sub-g{i}", email=f"race-g{i}@example.com", email_verified=True)

        async def attempt(claims: GoogleClaims = claims) -> int:
            async with committing_sessions() as session:
                user = await login_with_google(session, claims)
                await session.commit()
                return user.id

        ids = await asyncio.gather(attempt(), attempt(), attempt())
        assert len(set(ids)) == 1
        async with committing_sessions() as check:
            assert await count(check, User, User.email == claims.email) == 1
            assert await count(check, UserIdentity, UserIdentity.provider_user_id == claims.sub) == 1


# linking and unlinking from the profile (rule 2) -------------------------------


async def test_link_requires_the_password_when_the_account_has_one(user_client, google, db):
    credential = google.token("sub-t", "someone.else@example.com")
    missing = await user_client.post("/api/auth/google/link", json={"credential": credential})
    assert missing.status_code == 401
    wrong = await user_client.post("/api/auth/google/link", json={"credential": credential, "password": "wrong-one"})
    assert wrong.status_code == 401
    assert await identity_for(db, "sub-t") is None

    ok = await user_client.post("/api/auth/google/link", json={"credential": credential, "password": "password123"})
    assert ok.status_code == 200
    assert ok.json()["google_linked"] is True and ok.json()["has_password"] is True
    assert (await user_client.get("/api/me")).json()["email"] == "test@example.com"  # email unchanged


async def test_link_conflicts(user_client, google, db):
    body = {"credential": google.token("sub-t", "test@example.com"), "password": "password123"}
    assert (await user_client.post("/api/auth/google/link", json=body)).status_code == 200
    again = await user_client.post("/api/auth/google/link", json=body)
    assert again.status_code == 409 and again.json()["error"]["code"] == "google_already_linked"

    # that Google account belongs to test@; the admin cannot claim it
    await user_client.post("/api/auth/logout")
    user_client.cookies.clear()
    await user_client.post("/api/auth/login", json={"email": "admin@example.com", "password": "password123"})
    use_csrf(user_client)
    stolen = await user_client.post("/api/auth/google/link", json={**body})
    assert stolen.status_code == 409 and stolen.json()["error"]["code"] == "google_account_in_use"
    # and the failed insert did not break the session
    assert (await user_client.get("/api/me")).status_code == 200


async def test_link_verifies_the_email_when_google_confirms_the_same_address(client, google, db):
    await client.post("/api/auth/register", json=REG)
    use_csrf(client)
    body = {"credential": google.token("sub-v", REG["email"]), "password": REG["password"]}
    assert (await client.post("/api/auth/google/link", json=body)).status_code == 200
    assert (await client.get("/api/me")).json()["email_verified"] is True


async def test_cannot_unlink_the_last_login_method(client, google, db):
    await google_login(client, google, "sub-1", "g@example.com")
    use_csrf(client)
    response = await client.delete("/api/auth/google")
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "last_login_method"
    assert await identity_for(db, "sub-1") is not None

    # after setting a password the link can go
    assert (await client.put("/api/me/password", json={"new_password": "now I have one"})).status_code == 200
    use_csrf(client)
    assert (await client.delete("/api/auth/google")).status_code == 204
    assert await identity_for(db, "sub-1") is None
    me = (await client.get("/api/me")).json()
    assert me["has_password"] is True and me["google_linked"] is False


async def test_unlink_with_a_password_is_allowed_and_unlinking_nothing_is_404(user_client, google):
    assert (await user_client.delete("/api/auth/google")).status_code == 404
    body = {"credential": google.token("sub-t", "test@example.com"), "password": "password123"}
    await user_client.post("/api/auth/google/link", json=body)
    assert (await user_client.delete("/api/auth/google")).status_code == 204


# deleting a Google-only account --------------------------------------------------


async def test_delete_google_only_account_needs_a_fresh_matching_credential(client, google, db):
    await google_login(client, google, "sub-1", "g@example.com")
    use_csrf(client)
    none = await client.request("DELETE", "/api/me", json={})
    assert none.status_code == 401 and none.json()["error"]["code"] == "reauth_required"
    other = await client.request("DELETE", "/api/me", json={"credential": google.token("sub-other", "g@example.com")})
    assert other.status_code == 401
    assert await count(db, User) == 1

    ok = await client.request("DELETE", "/api/me", json={"credential": google.token("sub-1", "g@example.com")})
    assert ok.status_code == 204
    assert await count(db, User) == 0
    assert await count(db, UserIdentity) == 0  # cascaded
    assert await count(db, UserSession) == 0
