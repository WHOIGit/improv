"""Sample-level geolocation (lat, lon, depth).

Revision ID: 003
Revises: 002
Create Date: 2026-11-10
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "003"
down_revision: str | None = "002"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column("samples", sa.Column("lat", sa.Float(), nullable=True))
    op.add_column("samples", sa.Column("lon", sa.Float(), nullable=True))
    op.add_column("samples", sa.Column("depth", sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column("samples", "depth")
    op.drop_column("samples", "lon")
    op.drop_column("samples", "lat")
