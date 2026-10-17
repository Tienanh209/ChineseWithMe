from fastapi import APIRouter
from sqlalchemy import text

from app.deps import Db
from app.errors import AppError

router = APIRouter(tags=["health"])


@router.get("/health")
async def health(db: Db) -> dict[str, str]:
    try:
        await db.execute(text("SELECT 1"))
    except Exception as exc:
        raise AppError(503, "db_unavailable", "Database is not reachable.") from exc
    return {"status": "ok", "db": "ok"}
