from functools import lru_cache
from typing import Literal

from pydantic import SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEV_SECRET = "dev-insecure-secret-change-me"  # noqa: S105 (refused in prod by the validator below)


class Settings(BaseSettings):
    """All configuration comes from the environment (or backend/.env in development)."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    env: Literal["dev", "test", "prod"] = "dev"
    # SQLAlchemy URL. golang-migrate uses its own MIGRATE_DATABASE_URL (postgres://...).
    database_url: str = "postgresql+asyncpg://app:app@localhost:5432/app"
    db_pool_size: int = 10

    secret_key: SecretStr = SecretStr(DEV_SECRET)
    session_ttl_days: int = 30
    cookie_secure: bool = True

    # Where the SPA is served; used for links in emails.
    public_url: str = "http://localhost:5173"

    # OAuth client ID of the Google Identity Services button. Empty disables Google sign-in.
    google_client_id: str = ""

    # "console" logs the message (dev only), "smtp" sends it, "memory" keeps it in a list (tests).
    mail_backend: Literal["console", "smtp", "memory"] = "console"
    mail_from: str = "Học tiếng Trung <no-reply@localhost>"
    smtp_host: str = "localhost"
    smtp_port: int = 1025
    smtp_user: str = ""
    smtp_password: SecretStr = SecretStr("")
    smtp_starttls: bool = False

    verify_token_ttl_hours: int = 48
    reset_token_ttl_minutes: int = 60

    # Public base for bucket-relative audio_path values: "/audio" (served by nginx from
    # dev-audio/ in development) or the CDN in production, e.g. https://cdn.example.com/audio
    audio_base_url: str = "/audio"

    # Empty in the usual setup: nginx (prod) or the Vite proxy (dev) serve SPA and API
    # from one origin. List extra origins only if the SPA is hosted elsewhere.
    cors_origins: list[str] = []

    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    log_json: bool = True

    @model_validator(mode="after")
    def _prod_needs_real_secret(self) -> "Settings":
        if self.env == "prod":
            if self.secret_key.get_secret_value() == DEV_SECRET or len(self.secret_key.get_secret_value()) < 32:
                raise ValueError("SECRET_KEY must be set to a random value of at least 32 characters in prod")
            if not self.cookie_secure:
                raise ValueError("COOKIE_SECURE must be true in prod")
            if self.mail_backend != "smtp":
                raise ValueError("MAIL_BACKEND must be smtp in prod")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
