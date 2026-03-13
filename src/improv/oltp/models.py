"""SQLAlchemy ORM models for the OLTP store.

Four tables: Instrument, Sample, Dataset, DatasetSpan.
No per-image rows here — images live in the columnar store.

Sample.meta maps to the 'metadata' column (JSON/JSONB). The Python attribute
is named 'meta' to avoid shadowing SQLAlchemy's DeclarativeBase.metadata.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, JSON, String, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Instrument(Base):
    __tablename__ = "instruments"

    name: Mapped[str] = mapped_column(String, primary_key=True)
    type: Mapped[str] = mapped_column(String, nullable=False)
    serial_number: Mapped[str | None] = mapped_column(String, nullable=True)
    deployment_start: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    deployment_end: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    description: Mapped[str | None] = mapped_column(String, nullable=True)

    samples: Mapped[list[Sample]] = relationship("Sample", back_populates="instrument_rel")

    def __repr__(self) -> str:
        return f"<Instrument {self.name!r} type={self.type!r}>"


class Sample(Base):
    """One row per acquisition event (discrete instruments only).

    time_start/time_end scope columnar queries — required fields.
    meta holds instrument state + water-source context as JSON.
    """

    __tablename__ = "samples"

    sample_id: Mapped[str] = mapped_column(String, primary_key=True)
    instrument: Mapped[str] = mapped_column(
        String, ForeignKey("instruments.name"), nullable=False
    )
    time_start: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    time_end: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    quality_flag: Mapped[int | None] = mapped_column(Integer, nullable=True)
    alternate_sample_id: Mapped[str | None] = mapped_column(String, nullable=True)
    storage_key: Mapped[str | None] = mapped_column(String, nullable=True)
    # 'metadata' column; Python attribute named 'meta' to avoid ORM name clash
    meta: Mapped[dict] = mapped_column("metadata", JSON, nullable=False, default=dict)

    instrument_rel: Mapped[Instrument] = relationship(
        "Instrument", back_populates="samples"
    )

    def __repr__(self) -> str:
        return f"<Sample {self.sample_id!r} instrument={self.instrument!r}>"


class Dataset(Base):
    __tablename__ = "datasets"

    dataset_id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str | None] = mapped_column(String, nullable=True)

    __table_args__ = (UniqueConstraint("name", name="uq_datasets_name"),)

    spans: Mapped[list[DatasetSpan]] = relationship(
        "DatasetSpan", back_populates="dataset"
    )

    def __repr__(self) -> str:
        return f"<Dataset {self.name!r}>"


class DatasetSpan(Base):
    """A (instrument, time_start, time_end) span defining dataset membership.

    Dataset membership is derived from spans — no per-image tagging required.
    """

    __tablename__ = "dataset_spans"

    span_id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    dataset_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("datasets.dataset_id"), nullable=False
    )
    # instrument matches partition key value in db-utils (not an FK)
    instrument: Mapped[str] = mapped_column(String, nullable=False)
    time_start: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    time_end: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    dataset: Mapped[Dataset] = relationship("Dataset", back_populates="spans")

    def __repr__(self) -> str:
        return (
            f"<DatasetSpan instrument={self.instrument!r} "
            f"{self.time_start}–{self.time_end}>"
        )
