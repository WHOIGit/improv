"""Classifier taxonomy (label-map) table.

Revision ID: 002
Revises: 001
Create Date: 2026-07-06
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "002"
down_revision: str | None = "001"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "classifier_taxonomy",
        sa.Column("taxonomy_id", sa.String(36), nullable=False),
        sa.Column("classifier", sa.String(), nullable=False),
        sa.Column("model_version", sa.String(), nullable=False),
        sa.Column("class_names", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("taxonomy_id"),
        sa.UniqueConstraint(
            "classifier", "model_version", name="uq_classifier_taxonomy_version"
        ),
    )
    op.create_index(
        "ix_classifier_taxonomy_classifier",
        "classifier_taxonomy",
        ["classifier"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_classifier_taxonomy_classifier", table_name="classifier_taxonomy"
    )
    op.drop_table("classifier_taxonomy")
