from __future__ import annotations

import uuid
from datetime import datetime, timezone

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from app.infra.database import Base


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Session(Base):
    __tablename__ = "sessions"

    id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid(native_uuid=True),
        primary_key=True,
        server_default=sa.text("gen_random_uuid()"),
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid(native_uuid=True),
        sa.ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    device_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid(native_uuid=True),
        sa.ForeignKey("devices.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    refresh_token_hash: Mapped[str] = mapped_column(
        sa.String(length=64), unique=True, nullable=False
    )
    previous_token_hash: Mapped[str | None] = mapped_column(
        sa.String(length=64), nullable=True
    )
    issued_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        default=_utc_now,
    )
    expires_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False
    )
    last_activity_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        default=_utc_now,
    )
    revoked_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        default=_utc_now,
    )

    __table_args__ = (
        sa.Index("ix_sessions_user_id_revoked_at", "user_id", "revoked_at"),
        sa.Index("ix_sessions_device_id_revoked_at", "device_id", "revoked_at"),
    )
