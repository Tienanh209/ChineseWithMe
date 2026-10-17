from typing import Literal, Self
from zoneinfo import available_timezones

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from app.models import User

Level = Literal["A1", "A2", "B1", "B2", "C1", "C2"]
UiLang = Literal["vi", "en"]


class MeOut(BaseModel):
    id: int
    email: str
    email_verified: bool
    username: str | None
    display_name: str | None
    avatar_url: str | None
    target_level: Level
    ui_lang: str
    timezone: str
    role: str

    @classmethod
    def from_user(cls, user: User) -> "MeOut":
        return cls(
            id=user.id,
            email=user.email,
            email_verified=user.email_verified_at is not None,
            username=user.username,
            display_name=user.display_name,
            avatar_url=user.avatar_url,
            target_level=user.target_level,
            ui_lang=user.ui_lang,
            timezone=user.timezone,
            role=user.role,
        )


class MePatch(BaseModel):
    """Partial update. Omit a field to leave it unchanged; null is rejected."""

    model_config = ConfigDict(extra="forbid")

    target_level: Level | None = None
    ui_lang: UiLang | None = None
    timezone: str | None = None

    @field_validator("timezone")
    @classmethod
    def _known_timezone(cls, value: str | None) -> str | None:
        if value is not None and value not in available_timezones():
            raise ValueError("unknown IANA time zone")
        return value

    @model_validator(mode="after")
    def _no_nulls(self) -> Self:
        for name in self.model_fields_set:
            if getattr(self, name) is None:
                raise ValueError(f"{name} cannot be null")
        return self
