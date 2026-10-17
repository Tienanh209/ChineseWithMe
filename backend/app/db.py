from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import get_settings

_settings = get_settings()

# The engine connects lazily, so importing this module never touches the database.
engine = create_async_engine(
    _settings.database_url,
    pool_size=_settings.db_pool_size,
    pool_pre_ping=True,
)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def get_db() -> AsyncIterator[AsyncSession]:
    """One session per request. Routes that write call `await db.commit()` explicitly;
    anything not committed is rolled back when the session closes."""
    async with SessionLocal() as session:
        yield session
