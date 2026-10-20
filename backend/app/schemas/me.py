import re
from typing import Annotated, Literal, Self
from zoneinfo import available_timezones

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator, model_validator

from app.models import User

Level = Literal["A1", "A2", "B1", "B2", "C1", "C2"]
UiLang = Literal["vi", "en"]

USERNAME_RE = re.compile(r"^[A-Za-z0-9_.-]{3,32}$")
Password = Annotated[str, StringConstraints(min_length=8, max_length=128)]

# Fields a profile update may set to null to clear them.
_CLEARABLE = {"display_name", "username", "avatar_url"}


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
    has_password: bool
    google_linked: bool

    @classmethod
    def from_user(cls, user: User, *, has_password: bool, google_linked: bool) -> "MeOut":
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
            has_password=has_password,
            google_linked=google_linked,
        )


class MePatch(BaseModel):
    """Partial update. Omit a field to leave it unchanged. Only display_name, username and
    avatar_url may be set to null (to clear them)."""

    model_config = ConfigDict(extra="forbid")

    display_name: Annotated[str, StringConstraints(strip_whitespace=True, max_length=100)] | None = None
    username: str | None = None
    avatar_url: Annotated[str, StringConstraints(max_length=500)] | None = None
    target_level: Level | None = None
    ui_lang: UiLang | None = None
    timezone: str | None = None

    @field_validator("username")
    @classmethod
    def _valid_username(cls, value: str | None) -> str | None:
        if value is not None and not USERNAME_RE.match(value):
            raise ValueError("username must be 3 to 32 characters: letters, digits, '_', '.' or '-'")
        return value

    @field_validator("avatar_url")
    @classmethod
    def _https_avatar(cls, value: str | None) -> str | None:
        if value is not None and not value.startswith("https://"):
            raise ValueError("avatar_url must be an https URL")
        return value

    @field_validator("timezone")
    @classmethod
    def _known_timezone(cls, value: str | None) -> str | None:
        if value is not None and value not in available_timezones():
            raise ValueError("unknown IANA time zone")
        return value

    @model_validator(mode="after")
    def _no_nulls(self) -> Self:
        for name in self.model_fields_set - _CLEARABLE:
            if getattr(self, name) is None:
                raise ValueError(f"{name} cannot be null")
        return self


class ChangePasswordIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # Required when the account already has a password; absent for Google-only accounts.
    current_password: str | None = Field(default=None, max_length=128)
    new_password: Password


class DeleteAccountIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # Proof of identity: the password, or for a Google-only account a fresh Google credential.
    password: str | None = Field(default=None, max_length=128)
    credential: str | None = Field(default=None, max_length=4096)
