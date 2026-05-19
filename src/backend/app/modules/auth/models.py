from __future__ import annotations

import uuid

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.infra.database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid(native_uuid=True),
        primary_key=True,
        server_default=sa.text("gen_random_uuid()"),
    )
    email: Mapped[str] = mapped_column(
        sa.String(length=255), unique=True, index=True, nullable=False
    )
    account_status: Mapped[str] = mapped_column(
        sa.String(length=32),
        nullable=False,
        server_default=sa.text("'active'"),
    )
    created_at: Mapped[sa.DateTime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.text("now()"),
    )
    updated_at: Mapped[sa.DateTime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.text("now()"),
        onupdate=sa.text("now()"),
    )

    __table_args__ = (
        sa.CheckConstraint(
            "account_status IN ('inactive', 'active', 'suspended')",
            name="ck_users_account_status",
        ),
    )


class Device(Base):
    __tablename__ = "devices"

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
    credential_id: Mapped[str] = mapped_column(
        sa.String(length=255), unique=True, nullable=False
    )
    public_key: Mapped[bytes] = mapped_column(sa.LargeBinary(), nullable=False)
    sign_count: Mapped[int] = mapped_column(
        sa.Integer, nullable=False, server_default=sa.text("0")
    )
    device_name: Mapped[str | None] = mapped_column(
        sa.String(length=255), nullable=True
    )
    device_metadata: Mapped[dict] = mapped_column(
        JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")
    )
    is_active: Mapped[bool] = mapped_column(
        sa.Boolean, nullable=False, server_default=sa.text("true")
    )
    last_login_at: Mapped[sa.DateTime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[sa.DateTime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.text("now()"),
    )

    __table_args__ = (sa.Index("ix_devices_user_id_is_active", "user_id", "is_active"),)
