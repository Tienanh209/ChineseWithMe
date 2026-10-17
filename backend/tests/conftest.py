"""Tests run against a real, migrated Postgres (TEST_DATABASE_URL, default app_test).
Each test runs inside a transaction that is rolled back, so the database stays empty;
route code calling commit() only releases a savepoint.
"""

import os

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL", "postgresql+asyncpg://app:app@localhost:5432/app_test")
os.environ.update(ENV="dev", DATABASE_URL=TEST_DATABASE_URL, COOKIE_SECURE="false", LOG_JSON="false")

import pytest  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine  # noqa: E402
from sqlalchemy.pool import NullPool  # noqa: E402

from app.db import get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.security import CSRF_COOKIE, CSRF_HEADER  # noqa: E402
from app.seed import seed  # noqa: E402


@pytest.fixture(scope="session")
async def engine():
    engine = create_async_engine(TEST_DATABASE_URL, poolclass=NullPool)
    yield engine
    await engine.dispose()


@pytest.fixture
async def db(engine):
    async with engine.connect() as conn:
        outer = await conn.begin()
        session = AsyncSession(bind=conn, expire_on_commit=False, join_transaction_mode="create_savepoint")
        try:
            yield session
        finally:
            await session.close()
            await outer.rollback()


@pytest.fixture
async def client(db):
    app.dependency_overrides[get_db] = lambda: db
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client
    app.dependency_overrides.clear()


@pytest.fixture
async def seeded(db):
    assert await seed(db), "test database must start empty"


@pytest.fixture
async def user_client(client, seeded):
    """Client signed in as the seed test user, sending the CSRF header like the SPA does."""
    response = await client.post("/api/dev/login", json={"email": "test@example.com"})
    assert response.status_code == 200
    client.headers[CSRF_HEADER] = client.cookies[CSRF_COOKIE]
    return client
