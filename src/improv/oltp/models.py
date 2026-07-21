"""SQLAlchemy ORM models for the OLTP store.

Five tables: Instrument, Sample, Dataset, DatasetSpan, IngestTask.
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


class IngestTask(Base):
    """Tracks a unit of ingest work for idempotency and failure recovery.

    The task_id is producer-defined: a bin ID for IFCB, a filename or time
    window for continuous instruments, etc. The producer chooses whatever
    granularity makes sense for its work units.

    Status transitions: pending → pending (heartbeat), pending → complete,
    pending → failed. Clients can DELETE tasks to allow re-registration
    after cleanup.
    """

    __tablename__ = "ingest_tasks"

    task_id: Mapped[str] = mapped_column(String, primary_key=True)
    instrument: Mapped[str | None] = mapped_column(String, nullable=True)
    status: Mapped[str] = mapped_column(
        String, nullable=False, default="pending"
    )  # pending | complete | failed
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    def __repr__(self) -> str:
        return f"<IngestTask {self.task_id!r} status={self.status!r}>"


class ClassifierTaxonomy(Base):
    """Ordered class-name list (label-map) for one classifier + model version.

    A machine classification record stores scores positionally (a float vector)
    and the winner as an integer index; the class names live here, keyed by
    (classifier, model_version), where classifier is the plugin kind
    (e.g. "ifcb_cnn_classification"). Index position in class_names is the class
    id. Append-only: any change to the class list/order requires a new
    model_version, so historical vectors decode against their own version.
    """

    __tablename__ = "classifier_taxonomy"
    __table_args__ = (
        UniqueConstraint(
            "classifier", "model_version", name="uq_classifier_taxonomy_version"
        ),
    )

    taxonomy_id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    classifier: Mapped[str] = mapped_column(String, nullable=False, index=True)
    model_version: Mapped[str] = mapped_column(String, nullable=False)
    class_names: Mapped[list] = mapped_column(JSON, nullable=False)  # ordered list[str]
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    def __repr__(self) -> str:
        return (
            f"<ClassifierTaxonomy {self.classifier!r} {self.model_version!r} "
            f"n_classes={len(self.class_names)}>"
        )
