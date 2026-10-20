from sqlalchemy import func, select

from app.models import (
    ExerciseAttempt,
    GameSession,
    Lesson,
    User,
    UserLessonProgress,
    UserSession,
    UserVocabProgress,
    VocabReviewLog,
    Vocabulary,
)
from app.security import CSRF_HEADER
from tests.conftest import use_csrf


async def reload_user(db, email="test@example.com") -> User:
    return await db.scalar(select(User).where(User.email == email).execution_options(populate_existing=True))


async def test_me_requires_sign_in(client):
    response = await client.get("/api/me")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "not_authenticated"


async def test_get_me(user_client):
    response = await user_client.get("/api/me")
    assert response.status_code == 200
    body = response.json()
    assert body["email"] == "test@example.com"
    assert body["target_level"] == "A1"
    assert body["ui_lang"] == "vi"
    assert body["timezone"] == "Asia/Ho_Chi_Minh"
    assert body["email_verified"] is True
    assert body["has_password"] is True
    assert body["google_linked"] is False
    assert "password_hash" not in body


async def test_patch_me_saves_level_language_and_timezone(user_client, db):
    response = await user_client.patch(
        "/api/me", json={"target_level": "B1", "ui_lang": "en", "timezone": "Asia/Taipei"}
    )
    assert response.status_code == 200
    assert response.json()["target_level"] == "B1"
    user = await reload_user(db)
    assert (user.target_level, user.ui_lang, user.timezone) == ("B1", "en", "Asia/Taipei")


async def test_patch_me_profile_fields_and_clearing(user_client):
    response = await user_client.patch(
        "/api/me",
        json={"display_name": "  Anh  ", "username": "Anh_99", "avatar_url": "https://img.example.com/a.png"},
    )
    assert response.status_code == 200
    body = response.json()
    assert (body["display_name"], body["username"], body["avatar_url"]) == (
        "Anh",
        "Anh_99",
        "https://img.example.com/a.png",
    )
    cleared = await user_client.patch("/api/me", json={"display_name": "", "username": None, "avatar_url": None})
    body = cleared.json()
    assert (body["display_name"], body["username"], body["avatar_url"]) == (None, None, None)


async def test_username_is_unique_ignoring_case(user_client):
    # "admin" belongs to the seed admin user.
    response = await user_client.patch("/api/me", json={"username": "ADMIN"})
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "username_taken"
    # the failed update did not poison the session
    assert (await user_client.patch("/api/me", json={"username": "fresh_name"})).status_code == 200


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
        {"timezone": None},
        {"role": "admin"},
        {"username": "ab"},
        {"username": "x" * 33},
        {"username": "has space"},
        {"avatar_url": "http://insecure.example.com/a.png"},
        {"avatar_url": "javascript:alert(1)"},
        {"display_name": "x" * 101},
    ):
        response = await user_client.patch("/api/me", json=body)
        assert response.status_code == 422, body
        error = response.json()["error"]
        assert error["code"] == "validation_error"
        assert isinstance(error["details"], list)


async def test_change_password_signs_out_other_sessions_and_keeps_this_one(user_client, client, db):
    other = type(client)(transport=client._transport, base_url="http://test")
    async with other:
        assert (
            await other.post("/api/auth/login", json={"email": "test@example.com", "password": "password123"})
        ).status_code == 200
        response = await user_client.put(
            "/api/me/password", json={"current_password": "password123", "new_password": "a-new-password"}
        )
        assert response.status_code == 200
        use_csrf(user_client)  # the session and its CSRF cookie were replaced
        assert (await user_client.get("/api/me")).status_code == 200
        assert (await other.get("/api/me")).status_code == 401
    # old password no longer works, new one does
    fresh = type(client)(transport=client._transport, base_url="http://test")
    async with fresh:
        bad = await fresh.post("/api/auth/login", json={"email": "test@example.com", "password": "password123"})
        assert bad.status_code == 401
        good = await fresh.post("/api/auth/login", json={"email": "test@example.com", "password": "a-new-password"})
        assert good.status_code == 200


async def test_change_password_needs_the_current_one(user_client):
    for body in (
        {"new_password": "a-new-password"},
        {"current_password": "wrong", "new_password": "a-new-password"},
    ):
        response = await user_client.put("/api/me/password", json=body)
        assert response.status_code == 401
        assert response.json()["error"]["code"] == "invalid_credentials"
    short = await user_client.put("/api/me/password", json={"current_password": "password123", "new_password": "short"})
    assert short.status_code == 422


async def test_delete_account_requires_password_and_cascades(user_client, db):
    user = await reload_user(db)
    vocab_id = await db.scalar(select(Vocabulary.id).limit(1))
    lesson_id = await db.scalar(select(Lesson.id).limit(1))
    db.add_all(
        [
            UserVocabProgress(user_id=user.id, vocabulary_id=vocab_id),
            VocabReviewLog(user_id=user.id, vocabulary_id=vocab_id, source="flashcard", rating=3),
            UserLessonProgress(user_id=user.id, lesson_id=lesson_id),
            ExerciseAttempt(user_id=user.id, lesson_id=lesson_id, total=2),
            GameSession(user_id=user.id, game_type="match"),
        ]
    )
    await db.flush()
    tables = (UserVocabProgress, VocabReviewLog, UserLessonProgress, ExerciseAttempt, GameSession, UserSession)

    async def rows(model):
        return await db.scalar(select(func.count()).select_from(model).where(model.user_id == user.id))

    assert [await rows(t) for t in tables] == [1, 1, 1, 1, 1, 1]

    assert (await user_client.request("DELETE", "/api/me", json={})).status_code == 401
    assert (await user_client.request("DELETE", "/api/me", json={"password": "wrong"})).status_code == 401
    assert await reload_user(db) is not None
    response = await user_client.request("DELETE", "/api/me", json={"password": "password123"})
    assert response.status_code == 204
    assert await reload_user(db) is None
    assert [await rows(t) for t in tables] == [0, 0, 0, 0, 0, 0]
    assert (await user_client.get("/api/me")).status_code == 401
    # shared content stays
    assert await db.scalar(select(func.count()).select_from(Vocabulary)) > 0
