from __future__ import annotations

import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from app.infra.database import Base


class Vault(Base):
    __tablename__ = "vaults"

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
    service_name: Mapped[str] = mapped_column(sa.String(length=255), nullable=False)
    login_name: Mapped[str] = mapped_column(sa.String(length=255), nullable=False)
    password_blob: Mapped[bytes] = mapped_column(sa.LargeBinary(), nullable=False)
    notes_blob: Mapped[bytes | None] = mapped_column(sa.LargeBinary(), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.text("now()"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.text("now()"),
        onupdate=sa.text("now()"),
    )
