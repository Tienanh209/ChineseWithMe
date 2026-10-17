from datetime import datetime

from sqlalchemy import BigInteger, ForeignKey, LargeBinary, Text
from sqlalchemy.dialects.postgresql import CITEXT
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, CefrLevel, created_at_column, db_default, id_column, updated_at_column


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = id_column()
    username: Mapped[str | None] = mapped_column(CITEXT)
    email: Mapped[str] = mapped_column(CITEXT)
    email_verified_at: Mapped[datetime | None]
    password_hash: Mapped[str | None] = mapped_column(Text)
    display_name: Mapped[str | None] = mapped_column(Text)
    avatar_url: Mapped[str | None] = mapped_column(Text)
    target_level: Mapped[str] = mapped_column(CefrLevel, server_default=db_default())
    ui_lang: Mapped[str] = mapped_column(Text, server_default=db_default())
    timezone: Mapped[str] = mapped_column(Text, server_default=db_default())
    role: Mapped[str] = mapped_column(Text, server_default=db_default())
    created_at: Mapped[datetime] = created_at_column()
    updated_at: Mapped[datetime] = updated_at_column()

    identities: Mapped[list["UserIdentity"]] = relationship(back_populates="user", lazy="raise", passive_deletes=True)


class UserIdentity(Base):
    __tablename__ = "user_identities"

    id: Mapped[int] = id_column()
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"))
    provider: Mapped[str] = mapped_column(Text)
    provider_user_id: Mapped[str] = mapped_column(Text)
    email: Mapped[str | None] = mapped_column(CITEXT)
    created_at: Mapped[datetime] = created_at_column()
    last_login_at: Mapped[datetime | None]

    user: Mapped[User] = relationship(back_populates="identities", lazy="raise")


class UserSession(Base):
    """A login session (table `sessions`). Named to avoid confusion with the SQLAlchemy Session."""

    __tablename__ = "sessions"

    id: Mapped[int] = id_column()
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"))
    token_hash: Mapped[bytes] = mapped_column(LargeBinary)
    created_at: Mapped[datetime] = created_at_column()
    expires_at: Mapped[datetime]
    last_seen_at: Mapped[datetime] = mapped_column(server_default=db_default())
    user_agent: Mapped[str | None] = mapped_column(Text)


class AuthToken(Base):
    __tablename__ = "auth_tokens"

    id: Mapped[int] = id_column()
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"))
    purpose: Mapped[str] = mapped_column(Text)
    token_hash: Mapped[bytes] = mapped_column(LargeBinary)
    email: Mapped[str] = mapped_column(CITEXT)
    created_at: Mapped[datetime] = created_at_column()
    expires_at: Mapped[datetime]
    used_at: Mapped[datetime | None]
