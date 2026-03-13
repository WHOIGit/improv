"""Tests for OLTP bulk registration helpers."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from improv.oltp.bulk import (
    bulk_add_dataset_spans,
    bulk_register_datasets,
    bulk_register_instruments,
    bulk_register_samples,
    ensure_tables,
)
from improv.oltp.models import Base, Dataset, DatasetSpan, Instrument, Sample

DEPLOY_START = datetime(2022, 1, 1, tzinfo=timezone.utc)
T1 = datetime(2024, 1, 15, 12, 0, tzinfo=timezone.utc)
T2 = datetime(2024, 1, 15, 12, 30, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# ensure_tables
# ---------------------------------------------------------------------------

def test_ensure_tables_creates_schema():
    """ensure_tables should create all four OLTP tables idempotently."""
    eng = create_engine("sqlite:///:memory:")
    ensure_tables(eng)
    ensure_tables(eng)  # second call must not raise
    # All four tables should exist (a query against each succeeds)
    with Session(eng) as s:
        assert s.execute(select(Instrument)).all() == []
        assert s.execute(select(Sample)).all() == []
        assert s.execute(select(Dataset)).all() == []
        assert s.execute(select(DatasetSpan)).all() == []
    eng.dispose()


# ---------------------------------------------------------------------------
# bulk_register_instruments
# ---------------------------------------------------------------------------

def test_bulk_register_instruments_inserts_rows(engine):
    bulk_register_instruments(engine, [
        {"name": "IFCB107", "type": "IFCB", "deployment_start": DEPLOY_START},
        {"name": "IFCB108", "type": "IFCB", "deployment_start": DEPLOY_START, "description": "Backup unit"},
    ])
    with Session(engine) as s:
        rows = s.execute(select(Instrument)).scalars().all()
    assert {r.name for r in rows} == {"IFCB107", "IFCB108"}
    assert next(r for r in rows if r.name == "IFCB108").description == "Backup unit"


def test_bulk_register_instruments_idempotent(engine):
    record = {"name": "IFCB107", "type": "IFCB", "deployment_start": DEPLOY_START}
    bulk_register_instruments(engine, [record])
    bulk_register_instruments(engine, [record])  # duplicate — must not raise or double-insert
    with Session(engine) as s:
        count = len(s.execute(select(Instrument)).scalars().all())
    assert count == 1


def test_bulk_register_instruments_empty(engine):
    bulk_register_instruments(engine, [])  # must not raise
    with Session(engine) as s:
        assert s.execute(select(Instrument)).scalars().all() == []


# ---------------------------------------------------------------------------
# bulk_register_samples
# ---------------------------------------------------------------------------

def _add_instrument(engine, name="IFCB107"):
    bulk_register_instruments(engine, [{"name": name, "type": "IFCB", "deployment_start": DEPLOY_START}])


def test_bulk_register_samples_inserts_rows(engine):
    _add_instrument(engine)
    bulk_register_samples(engine, [
        {"sample_id": "S001", "instrument": "IFCB107", "time_start": T1, "time_end": T2},
        {"sample_id": "S002", "instrument": "IFCB107", "time_start": T1, "time_end": T2,
         "quality_flag": 1, "meta": {"volume_sampled": 5.0}},
    ])
    with Session(engine) as s:
        rows = {r.sample_id: r for r in s.execute(select(Sample)).scalars().all()}
    assert set(rows) == {"S001", "S002"}
    assert rows["S002"].quality_flag == 1
    assert rows["S002"].meta["volume_sampled"] == 5.0


def test_bulk_register_samples_defaults_meta(engine):
    _add_instrument(engine)
    bulk_register_samples(engine, [
        {"sample_id": "S001", "instrument": "IFCB107", "time_start": T1, "time_end": T2},
    ])
    with Session(engine) as s:
        row = s.get(Sample, "S001")
    assert row.meta == {}


def test_bulk_register_samples_idempotent(engine):
    _add_instrument(engine)
    record = {"sample_id": "S001", "instrument": "IFCB107", "time_start": T1, "time_end": T2}
    bulk_register_samples(engine, [record])
    bulk_register_samples(engine, [record])
    with Session(engine) as s:
        count = len(s.execute(select(Sample)).scalars().all())
    assert count == 1


def test_bulk_register_samples_large_batch(engine):
    """300k-scale: verify chunking doesn't corrupt or lose rows."""
    _add_instrument(engine)
    n = 6_000  # two full chunks
    records = [
        {
            "sample_id": f"S{i:06d}",
            "instrument": "IFCB107",
            "time_start": T1,
            "time_end": T2,
        }
        for i in range(n)
    ]
    bulk_register_samples(engine, records)
    with Session(engine) as s:
        count = len(s.execute(select(Sample)).scalars().all())
    assert count == n


# ---------------------------------------------------------------------------
# bulk_register_datasets
# ---------------------------------------------------------------------------

def test_bulk_register_datasets_inserts_rows(engine):
    bulk_register_datasets(engine, [
        {"name": "NES-LTER-EN688"},
        {"name": "NES-LTER-EN700", "description": "Fall cruise"},
    ])
    with Session(engine) as s:
        rows = {r.name: r for r in s.execute(select(Dataset)).scalars().all()}
    assert set(rows) == {"NES-LTER-EN688", "NES-LTER-EN700"}
    assert rows["NES-LTER-EN700"].description == "Fall cruise"


def test_bulk_register_datasets_auto_generates_id(engine):
    bulk_register_datasets(engine, [{"name": "DS1"}])
    with Session(engine) as s:
        row = s.execute(select(Dataset)).scalar_one()
    assert row.dataset_id  # non-empty UUID was generated


def test_bulk_register_datasets_accepts_explicit_id(engine):
    bulk_register_datasets(engine, [{"name": "DS1", "dataset_id": "fixed-id-123"}])
    with Session(engine) as s:
        row = s.execute(select(Dataset)).scalar_one()
    assert row.dataset_id == "fixed-id-123"


def test_bulk_register_datasets_idempotent(engine):
    bulk_register_datasets(engine, [{"name": "DS1"}])
    bulk_register_datasets(engine, [{"name": "DS1"}])
    with Session(engine) as s:
        count = len(s.execute(select(Dataset)).scalars().all())
    assert count == 1


# ---------------------------------------------------------------------------
# bulk_add_dataset_spans
# ---------------------------------------------------------------------------

def test_bulk_add_dataset_spans_inserts_rows(engine):
    bulk_register_datasets(engine, [{"name": "DS1"}])
    bulk_add_dataset_spans(engine, "DS1", [
        {"instrument": "IFCB107", "time_start": T1, "time_end": T2},
        {"instrument": "IFCB108", "time_start": T1, "time_end": T2},
    ])
    with Session(engine) as s:
        spans = s.execute(select(DatasetSpan)).scalars().all()
    assert len(spans) == 2
    assert {sp.instrument for sp in spans} == {"IFCB107", "IFCB108"}


def test_bulk_add_dataset_spans_links_to_dataset(engine):
    bulk_register_datasets(engine, [{"name": "DS1", "dataset_id": "ds-fixed"}])
    bulk_add_dataset_spans(engine, "DS1", [
        {"instrument": "IFCB107", "time_start": T1, "time_end": T2},
    ])
    with Session(engine) as s:
        span = s.execute(select(DatasetSpan)).scalar_one()
    assert span.dataset_id == "ds-fixed"


def test_bulk_add_dataset_spans_missing_dataset_raises(engine):
    with pytest.raises(ValueError, match="not found"):
        bulk_add_dataset_spans(engine, "DOES_NOT_EXIST", [
            {"instrument": "IFCB107", "time_start": T1, "time_end": T2},
        ])


def test_bulk_add_dataset_spans_empty(engine):
    bulk_register_datasets(engine, [{"name": "DS1"}])
    bulk_add_dataset_spans(engine, "DS1", [])  # must not raise
    with Session(engine) as s:
        assert s.execute(select(DatasetSpan)).scalars().all() == []
