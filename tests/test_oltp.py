"""Tests for OLTP CRUD operations."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from improv.oltp.queries import (
    add_dataset_span,
    get_dataset,
    get_dataset_spans,
    get_instrument,
    get_sample,
    get_sample_by_alternate_id,
    register_dataset,
    register_instrument,
    register_sample,
    resolve_dataset_to_filters,
)

DEPLOY_START = datetime(2022, 1, 1, tzinfo=timezone.utc)
DEPLOY_END = datetime(2026, 12, 31, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# Instrument
# ---------------------------------------------------------------------------

def test_register_and_get_instrument(session):
    instr = register_instrument(
        session, "ALPHA", "TestCam", DEPLOY_START, description="Test camera"
    )
    session.commit()

    result = get_instrument(session, "ALPHA")
    assert result is not None
    assert result.name == "ALPHA"
    assert result.type == "TestCam"
    assert result.description == "Test camera"


def test_register_instrument_idempotent(session):
    i1 = register_instrument(session, "ALPHA", "TestCam", DEPLOY_START)
    i2 = register_instrument(session, "ALPHA", "TestCam", DEPLOY_START)
    session.commit()
    assert i1.name == i2.name


def test_get_instrument_not_found(session):
    assert get_instrument(session, "UNKNOWN") is None


# ---------------------------------------------------------------------------
# Sample
# ---------------------------------------------------------------------------

def test_register_and_get_sample(session):
    register_instrument(session, "ALPHA", "TestCam", DEPLOY_START)
    sample = register_sample(
        session,
        "SAMPLE_001",
        "ALPHA",
        datetime(2024, 1, 15, 12, 0, tzinfo=timezone.utc),
        datetime(2024, 1, 15, 12, 10, tzinfo=timezone.utc),
        meta={"volume_sampled": 5.0},
    )
    session.commit()

    result = get_sample(session, "SAMPLE_001")
    assert result is not None
    assert result.instrument == "ALPHA"
    assert result.meta["volume_sampled"] == 5.0


def test_register_sample_idempotent(session):
    register_instrument(session, "ALPHA", "TestCam", DEPLOY_START)
    ts = datetime(2024, 1, 15, 12, 0, tzinfo=timezone.utc)
    s1 = register_sample(session, "SAMPLE_001", "ALPHA", ts, ts)
    s2 = register_sample(session, "SAMPLE_001", "ALPHA", ts, ts)
    session.commit()
    assert s1.sample_id == s2.sample_id


def test_alternate_sample_id_lookup(session):
    register_instrument(session, "ALPHA", "TestCam", DEPLOY_START)
    ts = datetime(2024, 1, 15, 12, 0, tzinfo=timezone.utc)
    register_sample(
        session, "SAMPLE_001", "ALPHA", ts, ts, alternate_sample_id="ALT_001"
    )
    session.commit()

    result = get_sample_by_alternate_id(session, "ALT_001")
    assert result is not None
    assert result.sample_id == "SAMPLE_001"


def test_alternate_id_with_instrument_filter(session):
    register_instrument(session, "ALPHA", "TestCam", DEPLOY_START)
    register_instrument(session, "BETA", "TestCam2", DEPLOY_START)
    ts = datetime(2024, 1, 15, 12, 0, tzinfo=timezone.utc)
    register_sample(session, "A_001", "ALPHA", ts, ts, alternate_sample_id="SHARED")
    register_sample(session, "B_001", "BETA", ts, ts, alternate_sample_id="SHARED")
    session.commit()

    result = get_sample_by_alternate_id(session, "SHARED", instrument="BETA")
    assert result.sample_id == "B_001"


def test_get_sample_not_found(session):
    assert get_sample(session, "NONEXISTENT") is None


# ---------------------------------------------------------------------------
# Dataset
# ---------------------------------------------------------------------------

def test_register_and_get_dataset(session):
    ds = register_dataset(session, "MVCO_2024", description="MVCO deployment 2024")
    session.commit()

    result = get_dataset(session, "MVCO_2024")
    assert result is not None
    assert result.description == "MVCO deployment 2024"


def test_register_dataset_idempotent(session):
    d1 = register_dataset(session, "DS1")
    d2 = register_dataset(session, "DS1")
    session.commit()
    assert d1.dataset_id == d2.dataset_id


def test_add_and_get_spans(session):
    ts1 = datetime(2024, 1, 1, tzinfo=timezone.utc)
    ts2 = datetime(2024, 12, 31, tzinfo=timezone.utc)
    add_dataset_span(session, "MVCO_2024", "ALPHA", ts1, ts2)
    session.commit()

    spans = get_dataset_spans(session, "MVCO_2024")
    assert len(spans) == 1
    assert spans[0].instrument == "ALPHA"


def test_resolve_dataset_to_filters(session):
    ts1 = datetime(2024, 1, 1, tzinfo=timezone.utc)
    ts2 = datetime(2024, 6, 30, tzinfo=timezone.utc)
    ts3 = datetime(2024, 7, 1, tzinfo=timezone.utc)
    ts4 = datetime(2024, 12, 31, tzinfo=timezone.utc)
    add_dataset_span(session, "MULTI", "ALPHA", ts1, ts2)
    add_dataset_span(session, "MULTI", "BETA", ts3, ts4)
    session.commit()

    filters = resolve_dataset_to_filters(session, "MULTI")
    assert len(filters) == 2
    instruments = {f["instrument"] for f in filters}
    assert instruments == {"ALPHA", "BETA"}


def test_resolve_unknown_dataset_returns_empty(session):
    filters = resolve_dataset_to_filters(session, "DOES_NOT_EXIST")
    assert filters == []
