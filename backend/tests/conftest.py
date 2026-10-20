"""Tests run against a real, migrated Postgres (TEST_DATABASE_URL, default app_test).
Each test runs inside a transaction that is rolled back, so the database stays empty;
route code calling commit() only releases a savepoint.
"""

import os

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL", "postgresql+asyncpg://app:app@localhost:5432/app_test")
os.environ.update(
    ENV="dev",
    DATABASE_URL=TEST_DATABASE_URL,
    COOKIE_SECURE="false",
    LOG_JSON="false",
    MAIL_BACKEND="memory",
    GOOGLE_CLIENT_ID="test-client-id",
    PUBLIC_URL="http://test",
)

import pytest  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine  # noqa: E402
from sqlalchemy.pool import NullPool  # noqa: E402

from app.db import get_db  # noqa: E402
from app.errors import AppError  # noqa: E402
from app.main import app  # noqa: E402
from app.security import CSRF_COOKIE, CSRF_HEADER  # noqa: E402
from app.seed import TEST_PASSWORD, seed  # noqa: E402
from app.services import mailer, ratelimit  # noqa: E402
from app.services.google import GoogleClaims, get_google_verifier  # noqa: E402


@pytest.fixture(autouse=True)
def _clean_process_state():
    """Rate limit counters and the mail outbox live in process memory."""
    ratelimit.reset_all()
    mailer.outbox.clear()
    yield
    ratelimit.reset_all()
    mailer.outbox.clear()


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


def use_csrf(client: AsyncClient) -> None:
    """Send the CSRF header from the current cookie, like the SPA's api client does."""
    client.headers[CSRF_HEADER] = client.cookies[CSRF_COOKIE]


@pytest.fixture
async def user_client(client, seeded):
    """Client signed in as the seed test user."""
    response = await client.post("/api/auth/login", json={"email": "test@example.com", "password": TEST_PASSWORD})
    assert response.status_code == 200
    use_csrf(client)
    return client


class FakeGoogle:
    """Stands in for Google's token verification. token() mints a credential the fake accepts."""

    def __init__(self) -> None:
        self.tokens: dict[str, GoogleClaims] = {}

    def token(self, sub: str, email: str, *, verified: bool = True, name: str | None = "G User") -> str:
        credential = f"cred:{sub}:{email}:{verified}"
        self.tokens[credential] = GoogleClaims(
            sub=sub, email=email, email_verified=verified, name=name, picture="https://lh3.example.com/p.png"
        )
        return credential

    async def __call__(self, credential: str) -> GoogleClaims:
        try:
            return self.tokens[credential]
        except KeyError:
            raise AppError(401, "invalid_google_token", "Google sign-in could not be verified.") from None


@pytest.fixture
def google(client):
    fake = FakeGoogle()
    app.dependency_overrides[get_google_verifier] = lambda: fake
    return fake
