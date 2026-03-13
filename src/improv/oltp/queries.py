"""CRUD operations for the OLTP store."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy.orm import Session

from improv.oltp.models import Dataset, DatasetSpan, Instrument, Sample


# ---------------------------------------------------------------------------
# Instrument
# ---------------------------------------------------------------------------

def get_instrument(session: Session, name: str) -> Instrument | None:
    return session.get(Instrument, name)


def register_instrument(
    session: Session,
    name: str,
    type: str,
    deployment_start: datetime,
    serial_number: str | None = None,
    deployment_end: datetime | None = None,
    description: str | None = None,
) -> Instrument:
    """Create or return an existing Instrument record."""
    existing = session.get(Instrument, name)
    if existing is not None:
        return existing
    instrument = Instrument(
        name=name,
        type=type,
        deployment_start=deployment_start,
        serial_number=serial_number,
        deployment_end=deployment_end,
        description=description,
    )
    session.add(instrument)
    session.flush()
    return instrument


# ---------------------------------------------------------------------------
# Sample
# ---------------------------------------------------------------------------

def get_sample(session: Session, sample_id: str) -> Sample | None:
    return session.get(Sample, sample_id)


def get_sample_by_alternate_id(
    session: Session,
    alternate_id: str,
    instrument: str | None = None,
) -> Sample | None:
    q = session.query(Sample).filter(Sample.alternate_sample_id == alternate_id)
    if instrument is not None:
        q = q.filter(Sample.instrument == instrument)
    return q.first()


def register_sample(
    session: Session,
    sample_id: str,
    instrument: str,
    time_start: datetime,
    time_end: datetime,
    quality_flag: int | None = None,
    alternate_sample_id: str | None = None,
    storage_key: str | None = None,
    meta: dict | None = None,
) -> Sample:
    """Create or return an existing Sample record."""
    existing = session.get(Sample, sample_id)
    if existing is not None:
        return existing
    sample = Sample(
        sample_id=sample_id,
        instrument=instrument,
        time_start=time_start,
        time_end=time_end,
        quality_flag=quality_flag,
        alternate_sample_id=alternate_sample_id,
        storage_key=storage_key,
        meta=meta or {},
    )
    session.add(sample)
    session.flush()
    return sample


# ---------------------------------------------------------------------------
# Dataset
# ---------------------------------------------------------------------------

def get_dataset(session: Session, name: str) -> Dataset | None:
    return session.query(Dataset).filter(Dataset.name == name).first()


def register_dataset(
    session: Session,
    name: str,
    description: str | None = None,
) -> Dataset:
    """Create or return an existing Dataset record."""
    existing = get_dataset(session, name)
    if existing is not None:
        return existing
    dataset = Dataset(
        dataset_id=str(uuid.uuid4()),
        name=name,
        description=description,
    )
    session.add(dataset)
    session.flush()
    return dataset


def add_dataset_span(
    session: Session,
    dataset_name: str,
    instrument: str,
    time_start: datetime,
    time_end: datetime,
) -> DatasetSpan:
    """Add a time span to a dataset (creates dataset if it doesn't exist)."""
    dataset = register_dataset(session, dataset_name)
    span = DatasetSpan(
        span_id=str(uuid.uuid4()),
        dataset_id=dataset.dataset_id,
        instrument=instrument,
        time_start=time_start,
        time_end=time_end,
    )
    session.add(span)
    session.flush()
    return span


def get_dataset_spans(session: Session, dataset_name: str) -> list[DatasetSpan]:
    dataset = get_dataset(session, dataset_name)
    if dataset is None:
        return []
    return list(dataset.spans)


def resolve_dataset_to_filters(
    session: Session, dataset_name: str
) -> list[dict]:
    """Resolve a dataset name to a list of columnar query filter dicts.

    Returns [{instrument, time_start, time_end}, ...] — one entry per span.
    Use these directly as filters for store.read() or get_images() calls.
    """
    spans = get_dataset_spans(session, dataset_name)
    return [
        {
            "instrument": span.instrument,
            "time_start": span.time_start,
            "time_end": span.time_end,
        }
        for span in spans
    ]
