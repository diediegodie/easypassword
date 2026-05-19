"""add device_metadata and single active device constraint

Revision ID: 0002_device_metadata_single_dev
Revises: 0001_initial_schema
Create Date: 2026-05-19 00:00:00.000000
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision = "0002_device_metadata_single_dev"
down_revision = "0001_initial_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "devices",
        sa.Column(
            "device_metadata",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )

    op.create_index(
        "uq_devices_user_id_is_active",
        "devices",
        ["user_id"],
        unique=True,
        postgresql_where=sa.text("is_active = true"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_devices_user_id_is_active",
        table_name="devices",
    )
    op.drop_column("devices", "device_metadata")
