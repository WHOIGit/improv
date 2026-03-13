"""Initial schema — instruments, samples, datasets, dataset_spans.

Revision ID: 001
Revises:
Create Date: 2026-03-13
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "001"
down_revision: str | None = None
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "instruments",
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("type", sa.String(), nullable=False),
        sa.Column("serial_number", sa.String(), nullable=True),
        sa.Column("deployment_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deployment_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("description", sa.String(), nullable=True),
        sa.PrimaryKeyConstraint("name"),
    )

    op.create_table(
        "samples",
        sa.Column("sample_id", sa.String(), nullable=False),
        sa.Column("instrument", sa.String(), nullable=False),
        sa.Column("time_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("time_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("quality_flag", sa.Integer(), nullable=True),
        sa.Column("alternate_sample_id", sa.String(), nullable=True),
        sa.Column("storage_key", sa.String(), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(["instrument"], ["instruments.name"]),
        sa.PrimaryKeyConstraint("sample_id"),
    )
    op.create_index("ix_samples_instrument", "samples", ["instrument"])
    op.create_index(
        "ix_samples_alternate_id", "samples", ["alternate_sample_id"]
    )

    op.create_table(
        "datasets",
        sa.Column("dataset_id", sa.String(36), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("description", sa.String(), nullable=True),
        sa.PrimaryKeyConstraint("dataset_id"),
        sa.UniqueConstraint("name", name="uq_datasets_name"),
    )

    op.create_table(
        "dataset_spans",
        sa.Column("span_id", sa.String(36), nullable=False),
        sa.Column("dataset_id", sa.String(36), nullable=False),
        sa.Column("instrument", sa.String(), nullable=False),
        sa.Column("time_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("time_end", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["dataset_id"], ["datasets.dataset_id"]),
        sa.PrimaryKeyConstraint("span_id"),
    )


def downgrade() -> None:
    op.drop_table("dataset_spans")
    op.drop_table("datasets")
    op.drop_table("samples")
    op.drop_table("instruments")
