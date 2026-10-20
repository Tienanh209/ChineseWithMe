import json

import pytest
from sqlalchemy import func, select

from app.models import VocabGroup, Vocabulary
from app.routers.admin import MAX_IMPORT_BYTES, MAX_IMPORT_ROWS
from app.security import CSRF_HEADER
from tests.conftest import use_csrf

URL = "/api/admin/vocabulary/import"
# The seed already holds 你好, 學習 and 女, so the tests use words it does not have.
CSV = "traditional,pinyin,level,vi,en\n老師,lǎoshī,A1,giáo viên,teacher\n醫生,yi1sheng1,A2,bác sĩ,doctor\n"
WORDS = [{"traditional": "醫院", "pinyin": "yīyuàn", "level": "A1", "translations": {"en": "hospital"}}]


@pytest.fixture
async def admin_client(client, seeded):
    response = await client.post("/api/auth/login", json={"email": "admin@example.com", "password": "password123"})
    assert response.status_code == 200 and response.json()["role"] == "admin"
    use_csrf(client)
    return client


async def vocab_count(db) -> int:
    return await db.scalar(select(func.count()).select_from(Vocabulary))


async def test_requires_sign_in(client):
    response = await client.post(URL, content=CSV, headers={"Content-Type": "text/csv"})
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "not_authenticated"


async def test_requires_an_admin(user_client, db):
    before = await vocab_count(db)
    response = await user_client.post(URL, content=CSV, headers={"Content-Type": "text/csv"})
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "forbidden"
    assert await vocab_count(db) == before


async def test_csrf_is_enforced(admin_client):
    del admin_client.headers[CSRF_HEADER]
    response = await admin_client.post(URL, content=CSV, headers={"Content-Type": "text/csv"})
    assert response.status_code == 403 and response.json()["error"]["code"] == "csrf_failed"


async def test_csv_body_imports_and_reports(admin_client, db):
    before = await vocab_count(db)
    response = await admin_client.post(URL, content=CSV.encode(), headers={"Content-Type": "text/csv; charset=utf-8"})
    assert response.status_code == 200
    report = response.json()
    assert {k: report[k] for k in ("total", "created", "updated", "unchanged", "rejected")} == {
        "total": 2,
        "created": 1,
        "updated": 0,
        "unchanged": 0,
        "rejected": 1,
    }
    assert report["dry_run"] is False and report["rolled_back"] is False
    assert report["rejected_rows"] == [
        {"row": 3, "word": "醫生 (yi1sheng1)", "errors": ["pinyin: use tone marks (nǐ), not tone numbers (ni3)"]}
    ]
    assert await vocab_count(db) == before + 1


async def test_json_body_and_format_override(admin_client, db):
    json_body = json.dumps({"words": WORDS}, ensure_ascii=False).encode()
    response = await admin_client.post(URL, content=json_body, headers={"Content-Type": "application/json"})
    assert response.status_code == 200 and response.json()["created"] == 1

    # an unhelpful content type: the format query parameter decides
    response = await admin_client.post(URL + "?format=json", content=json_body, headers={"Content-Type": "text/plain"})
    assert response.status_code == 200 and response.json()["unchanged"] == 1


async def test_content_is_detected_when_the_type_says_nothing(admin_client):
    response = await admin_client.post(URL, content=CSV.encode(), headers={"Content-Type": "application/octet-stream"})
    assert response.status_code == 200 and response.json()["created"] == 1


async def test_utf8_bom_from_excel_is_accepted(admin_client):
    response = await admin_client.post(
        URL, content=b"\xef\xbb\xbf" + CSV.encode(), headers={"Content-Type": "text/csv"}
    )
    assert response.status_code == 200 and response.json()["created"] == 1


async def test_dry_run_saves_nothing(admin_client, db):
    before = await vocab_count(db)
    response = await admin_client.post(
        URL + "?dry_run=true&group=Preview", content=CSV, headers={"Content-Type": "text/csv"}
    )
    report = response.json()
    assert response.status_code == 200 and report["dry_run"] is True and report["created"] == 1
    assert await vocab_count(db) == before
    assert await db.scalar(select(func.count()).select_from(VocabGroup).where(VocabGroup.name == "Preview")) == 0


async def test_strict_rolls_everything_back_when_a_row_is_rejected(admin_client, db):
    before = await vocab_count(db)
    response = await admin_client.post(URL + "?strict=true", content=CSV, headers={"Content-Type": "text/csv"})
    report = response.json()
    assert response.status_code == 200 and report["rolled_back"] is True and report["rejected"] == 1
    assert await vocab_count(db) == before


async def test_group_parameter_is_repeatable(admin_client, db):
    await admin_client.post(URL + "?group=A&group=B", content=CSV, headers={"Content-Type": "text/csv"})
    names = set(await db.scalars(select(VocabGroup.name).where(VocabGroup.name.in_(["A", "B"]))))
    assert names == {"A", "B"}


@pytest.mark.parametrize(
    ("body", "content_type", "fragment"),
    [
        (b"", "text/csv", "empty"),
        (b'[{"a": ', "application/json", "invalid JSON"),
        (b"traditional,pinyin,level,en,colour\n", "text/csv", "unknown column"),
        (b"traditional,pinyin\n", "text/csv", "missing column"),
        (b'{"words": 5}', "application/json", "list of words"),
    ],
)
async def test_unreadable_files_are_a_400_with_the_reason(admin_client, db, body, content_type, fragment):
    before = await vocab_count(db)
    response = await admin_client.post(URL, content=body, headers={"Content-Type": content_type})
    assert response.status_code == 400
    error = response.json()["error"]
    assert error["code"] == "invalid_import_file" and fragment in error["message"]
    assert await vocab_count(db) == before


async def test_non_utf8_is_a_400(admin_client):
    response = await admin_client.post(URL, content="你好".encode("big5"), headers={"Content-Type": "text/csv"})
    assert response.status_code == 400
    assert "UTF-8" in response.json()["error"]["message"]


async def test_size_and_row_limits(admin_client):
    too_big = await admin_client.post(URL, content=b"x" * (MAX_IMPORT_BYTES + 1), headers={"Content-Type": "text/csv"})
    assert too_big.status_code == 413 and too_big.json()["error"]["code"] == "payload_too_large"

    many = json.dumps([{}] * (MAX_IMPORT_ROWS + 1)).encode()
    response = await admin_client.post(URL, content=many, headers={"Content-Type": "application/json"})
    assert response.status_code == 400 and "too many rows" in response.json()["error"]["message"]


async def test_an_unknown_format_is_rejected_by_validation(admin_client):
    response = await admin_client.post(URL + "?format=xml", content=CSV, headers={"Content-Type": "text/csv"})
    assert response.status_code == 422 and response.json()["error"]["code"] == "validation_error"
