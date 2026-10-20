from typing import Annotated

from pydantic import BaseModel, ConfigDict, EmailStr, Field, StringConstraints

from app.schemas.me import Level, Password, UiLang


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AuthConfig(BaseModel):
    google_client_id: str | None


class RegisterIn(_Strict):
    email: EmailStr
    password: Password
    display_name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)] | None = None
    # Carry the visitor's choices from before sign-up into the new account.
    ui_lang: UiLang | None = None
    target_level: Level | None = None


class LoginIn(_Strict):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class GoogleIn(_Strict):
    credential: str = Field(min_length=1, max_length=4096)


class GoogleLinkIn(GoogleIn):
    # Required when the account has a password: linking is a sensitive change.
    password: str | None = Field(default=None, max_length=128)


class TokenIn(_Strict):
    token: str = Field(min_length=1, max_length=200)


class ForgotPasswordIn(_Strict):
    email: EmailStr


class ResetPasswordIn(TokenIn):
    password: Password
