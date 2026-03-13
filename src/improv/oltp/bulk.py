"""Bulk registration helpers for the OLTP store (improv[db]).

Populates instruments, samples, and datasets directly via a SQLAlchemy
Engine — no HTTP, no running service required.

Usage::

    pip install improv[db]

    from sqlalchemy import create_engine
    from improv.oltp.bulk import bulk_register_samples

    engine = create_engine("postgresql+psycopg2://...")
    bulk_register_samples(engine, [
        {
            "sample_id": "D20240101T120000_IFCB107",
            "instrument": "IFCB107",
            "time_start": datetime(...),
            "time_end": datetime(...),
        },
        ...
    ])

All functions are idempotent: existing rows (matched by primary key or
unique constraint) are silently skipped.  Call ``ensure_tables`` once
at pipeline startup if the database may not yet be initialised.
"""

from __future__ import annotations

import uuid
from itertools import islice
from typing import Any

from sqlalchemy import Engine, insert, select
from sqlalchemy.orm import Session

from improv.oltp.models import Base, Dataset, DatasetSpan, Instrument, Sample

_CHUNK = 5_000


def ensure_tables(engine: Engine) -> None:
    """Create OLTP tables if they do not exist (idempotent).

    Equivalent to ``alembic upgrade head`` for the simple case where no
    migrations have been applied yet.  In production, prefer Alembic.
    """
    Base.metadata.create_all(engine)


def _chunks(seq: list, n: int):
    it = iter(seq)
    while batch := list(islice(it, n)):
        yield batch


def _normalize(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Ensure every row dict has the same key set (fill gaps with None).

    SQLAlchemy's executemany infers the column list from the first row, so
    rows with extra or missing keys produce wrong SQL.
    """
    all_keys: set[str] = set().union(*rows)
    return [{k: r.get(k) for k in all_keys} for r in rows]


def _insert_ignore(engine: Engine, model, rows: list[dict[str, Any]]) -> None:
    """Bulk INSERT … ON CONFLICT DO NOTHING, dialect-aware."""
    if not rows:
        return
    rows = _normalize(rows)
    table = model.__table__
    if engine.dialect.name == "postgresql":
        from sqlalchemy.dialects.postgresql import insert as pg_insert
        stmt = pg_insert(table).on_conflict_do_nothing()
    else:
        stmt = insert(table).prefix_with("OR IGNORE")
    with engine.begin() as conn:
        for batch in _chunks(rows, _CHUNK):
            conn.execute(stmt, batch)


def bulk_register_instruments(
    engine: Engine,
    records: list[dict[str, Any]],
) -> None:
    """Register instruments in bulk.  Existing rows (by ``name``) are skipped.

    Required keys per record:
        ``name`` (str), ``type`` (str), ``deployment_start`` (datetime)

    Optional keys:
        ``serial_number`` (str), ``deployment_end`` (datetime), ``description`` (str)
    """
    _insert_ignore(engine, Instrument, records)


def bulk_register_samples(
    engine: Engine,
    records: list[dict[str, Any]],
) -> None:
    """Register samples in bulk.  Existing rows (by ``sample_id``) are skipped.

    Required keys per record:
        ``sample_id`` (str), ``instrument`` (str),
        ``time_start`` (datetime), ``time_end`` (datetime)

    Optional keys:
        ``quality_flag`` (int), ``alternate_sample_id`` (str),
        ``storage_key`` (str), ``meta`` (dict)
    """
    # ORM attribute is 'meta'; DB column is 'metadata' — translate for Core insert.
    rows = []
    for r in records:
        row = dict(r)
        row["metadata"] = row.pop("meta", None) or {}
        rows.append(row)
    _insert_ignore(engine, Sample, rows)


def bulk_register_datasets(
    engine: Engine,
    records: list[dict[str, Any]],
) -> None:
    """Register datasets in bulk.  Existing rows (by ``name``) are skipped.

    Required keys per record:
        ``name`` (str)

    Optional keys:
        ``dataset_id`` (str, auto-generated UUID if absent),
        ``description`` (str)
    """
    rows = [{**r, "dataset_id": r.get("dataset_id") or str(uuid.uuid4())} for r in records]
    _insert_ignore(engine, Dataset, rows)


def bulk_add_dataset_spans(
    engine: Engine,
    dataset_name: str,
    spans: list[dict[str, Any]],
) -> None:
    """Add time spans to a named dataset.

    The dataset must already exist (register it with ``bulk_register_datasets``
    first).  Spans are always inserted as new rows — there is no deduplication.

    Required keys per span:
        ``instrument`` (str), ``time_start`` (datetime), ``time_end`` (datetime)
    """
    with Session(engine) as session:
        dataset = session.execute(
            select(Dataset).where(Dataset.name == dataset_name)
        ).scalar_one_or_none()
        if dataset is None:
            raise ValueError(f"Dataset {dataset_name!r} not found; register it first.")
        dataset_id = dataset.dataset_id

    rows = [
        {
            "span_id": str(uuid.uuid4()),
            "dataset_id": dataset_id,
            "instrument": s["instrument"],
            "time_start": s["time_start"],
            "time_end": s["time_end"],
        }
        for s in spans
    ]
    if not rows:
        return
    with engine.begin() as conn:
        conn.execute(insert(DatasetSpan.__table__), rows)
