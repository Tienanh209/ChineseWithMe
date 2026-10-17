from sqlalchemy import select

from app.models import User
from app.security import CSRF_HEADER


async def test_me_requires_sign_in(client):
    response = await client.get("/api/me")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "not_authenticated"


async def test_dev_login_sets_httponly_session_and_readable_csrf_cookie(client, seeded):
    response = await client.post("/api/dev/login", json={"email": "test@example.com"})
    assert response.status_code == 200
    cookies = response.headers.get_list("set-cookie")
    sid = next(c for c in cookies if c.startswith("sid="))
    csrf = next(c for c in cookies if c.startswith("csrf_token="))
    assert "HttpOnly" in sid and "SameSite=lax" in sid
    assert "HttpOnly" not in csrf


async def test_get_me(user_client):
    response = await user_client.get("/api/me")
    assert response.status_code == 200
    body = response.json()
    assert body["email"] == "test@example.com"
    assert body["target_level"] == "A1"
    assert body["ui_lang"] == "vi"
    assert body["timezone"] == "Asia/Ho_Chi_Minh"
    assert body["email_verified"] is True


async def test_patch_me_saves_level_language_and_timezone(user_client, db):
    response = await user_client.patch(
        "/api/me", json={"target_level": "B1", "ui_lang": "en", "timezone": "Asia/Taipei"}
    )
    assert response.status_code == 200
    assert response.json()["target_level"] == "B1"
    user = await db.scalar(
        select(User).where(User.email == "test@example.com").execution_options(populate_existing=True)
    )
    assert (user.target_level, user.ui_lang, user.timezone) == ("B1", "en", "Asia/Taipei")


async def test_patch_me_without_csrf_header_is_rejected(user_client):
    del user_client.headers[CSRF_HEADER]
    response = await user_client.patch("/api/me", json={"target_level": "B1"})
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "csrf_failed"


async def test_patch_me_with_wrong_csrf_header_is_rejected(user_client):
    user_client.headers[CSRF_HEADER] = "0" * 64
    assert (await user_client.patch("/api/me", json={"target_level": "B1"})).status_code == 403


async def test_patch_me_validation(user_client):
    for body in (
        {"target_level": "D1"},
        {"ui_lang": "fr"},
        {"timezone": "Mars/Olympus"},
        {"target_level": None},
        {"role": "admin"},
    ):
        response = await user_client.patch("/api/me", json=body)
        assert response.status_code == 422, body
        error = response.json()["error"]
        assert error["code"] == "validation_error"
        assert isinstance(error["details"], list)


async def test_logout_ends_session(user_client):
    assert (await user_client.post("/api/dev/logout")).status_code == 204
    assert (await user_client.get("/api/me")).status_code == 401
