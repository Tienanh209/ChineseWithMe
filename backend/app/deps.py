from datetime import UTC, datetime
from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models import User
from app.security import current_user, optional_user, require_admin

Db = Annotated[AsyncSession, Depends(get_db)]
CurrentUser = Annotated[User, Depends(current_user)]
OptionalUser = Annotated[User | None, Depends(optional_user)]
AdminUser = Annotated[User, Depends(require_admin)]


def get_now() -> datetime:
    """The current instant, as a dependency so tests can fix the clock."""
    return datetime.now(UTC)


Now = Annotated[datetime, Depends(get_now)]
