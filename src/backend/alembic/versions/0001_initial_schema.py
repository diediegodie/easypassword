"""initial schema

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-05-12 00:00:00.000000
"""

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "0001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")

    op.create_table(
        "users",
        sa.Column(
            "id",
            sa.Uuid(native_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column(
            "account_status",
            sa.String(length=32),
            server_default=sa.text("'active'"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "account_status IN ('inactive', 'active', 'suspended')",
            name="ck_users_account_status",
        ),
        sa.UniqueConstraint("email", name="uq_users_email"),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    op.create_table(
        "devices",
        sa.Column(
            "id",
            sa.Uuid(native_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("user_id", sa.Uuid(native_uuid=True), nullable=False),
        sa.Column("credential_id", sa.String(length=255), nullable=False),
        sa.Column("public_key", sa.LargeBinary(), nullable=False),
        sa.Column(
            "sign_count", sa.Integer(), server_default=sa.text("0"), nullable=False
        ),
        sa.Column("device_name", sa.String(length=255), nullable=True),
        sa.Column(
            "is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False
        ),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("credential_id", name="uq_devices_credential_id"),
    )
    op.create_index(
        "ix_devices_credential_id", "devices", ["credential_id"], unique=True
    )
    op.create_index("ix_devices_user_id", "devices", ["user_id"], unique=False)
    op.create_index(
        "ix_devices_user_id_is_active",
        "devices",
        ["user_id", "is_active"],
        unique=False,
    )

    op.create_table(
        "vaults",
        sa.Column(
            "id",
            sa.Uuid(native_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("user_id", sa.Uuid(native_uuid=True), nullable=False),
        sa.Column("service_name", sa.String(length=255), nullable=False),
        sa.Column("login_name", sa.String(length=255), nullable=False),
        sa.Column("password_blob", sa.LargeBinary(), nullable=False),
        sa.Column("notes_blob", sa.LargeBinary(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_vaults_user_id", "vaults", ["user_id"], unique=False)

    op.create_table(
        "sessions",
        sa.Column(
            "id",
            sa.Uuid(native_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("user_id", sa.Uuid(native_uuid=True), nullable=False),
        sa.Column("device_id", sa.Uuid(native_uuid=True), nullable=False),
        sa.Column("refresh_token_hash", sa.String(length=64), nullable=False),
        sa.Column("previous_token_hash", sa.String(length=64), nullable=True),
        sa.Column(
            "issued_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "last_activity_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["device_id"], ["devices.id"], ondelete="CASCADE"),
        sa.UniqueConstraint(
            "refresh_token_hash", name="uq_sessions_refresh_token_hash"
        ),
    )
    op.create_index(
        "ix_sessions_refresh_token_hash",
        "sessions",
        ["refresh_token_hash"],
        unique=True,
    )
    op.create_index("ix_sessions_user_id", "sessions", ["user_id"], unique=False)
    op.create_index("ix_sessions_device_id", "sessions", ["device_id"], unique=False)
    op.create_index(
        "ix_sessions_user_id_revoked_at",
        "sessions",
        ["user_id", "revoked_at"],
        unique=False,
    )
    op.create_index(
        "ix_sessions_device_id_revoked_at",
        "sessions",
        ["device_id", "revoked_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_sessions_device_id_revoked_at", table_name="sessions")
    op.drop_index("ix_sessions_user_id_revoked_at", table_name="sessions")
    op.drop_index("ix_sessions_device_id", table_name="sessions")
    op.drop_index("ix_sessions_user_id", table_name="sessions")
    op.drop_index("ix_sessions_refresh_token_hash", table_name="sessions")
    op.drop_table("sessions")

    op.drop_index("ix_vaults_user_id", table_name="vaults")
    op.drop_table("vaults")

    op.drop_index("ix_devices_user_id_is_active", table_name="devices")
    op.drop_index("ix_devices_user_id", table_name="devices")
    op.drop_index("ix_devices_credential_id", table_name="devices")
    op.drop_table("devices")

    op.drop_index("ix_users_email", table_name="users")
    op.drop_table("users")
