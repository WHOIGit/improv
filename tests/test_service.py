"""Integration tests for ImageService — real DuckDB + SQLite, no mocking."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from improv.models.image import ImageRecord
from improv.models.provenance import ProvenanceEnvelope
from improv.oltp.queries import (
    add_dataset_span,
    register_instrument,
    register_sample,
)

DEPLOY_START = datetime(2022, 1, 1, tzinfo=timezone.utc)
TS_JAN = datetime(2024, 1, 15, 12, 0, tzinfo=timezone.utc)
TS_FEB = datetime(2024, 2, 15, 12, 0, tzinfo=timezone.utc)


def alpha_record(suffix: str, ts: datetime = TS_JAN) -> ImageRecord:
    return ImageRecord(
        image_id=f"ALPHA_{ts.strftime('%Y%m%dT%H%M%S')}_{suffix}",
        timestamp=ts,
        instrument="ALPHA",
    )


def geo_envelope(image_id: str, lat: float, lon: float, ts: datetime = TS_JAN) -> ProvenanceEnvelope:
    return ProvenanceEnvelope(
        image_id=image_id,
        kind="geolocation",
        source="nav_v1",
        timestamp=ts,
        data={
            "lat": lat,
            "lon": lon,
            "source": "nav_v1",
            "version": "1.0",
            "computed_at": ts.isoformat(),
        },
        instrument="ALPHA",
    )


# ---------------------------------------------------------------------------
# Ingest + retrieval
# ---------------------------------------------------------------------------

def test_ingest_and_get_image(service):
    record = alpha_record("001")
    service.ingest_images([record])
    result = service.get_image(record.image_id)
    assert result is not None
    assert result.image_id == record.image_id


def test_ingest_provenance_and_retrieve(service):
    record = alpha_record("001")
    service.ingest_images([record])

    env = ProvenanceEnvelope(
        image_id=record.image_id,
        kind="features",
        source="ifcb-features-v2",
        timestamp=TS_JAN,
        data={"area": 150.0},
        instrument="ALPHA",
    )
    service.ingest_provenance([env])

    results = service.get_provenance(record.image_id)
    assert len(results) == 1
    assert results[0].data["area"] == 150.0


def test_ingest_provenance_plugin_dual_write(service, store_with_tables):
    """geolocation plugin should dual-write to geolocation_index."""
    record = alpha_record("001")
    service.ingest_images([record])

    env = geo_envelope(record.image_id, lat=41.5, lon=-70.5)
    service.ingest_provenance([env])

    from improv.store.indexes import query_spatial
    ids = query_spatial(store_with_tables, 41.0, 42.0, -71.0, -70.0)
    assert record.image_id in ids


def test_query_images_time_range(service):
    r1 = alpha_record("001", TS_JAN)
    r2 = alpha_record("002", TS_FEB)
    service.ingest_images([r1, r2])

    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    end = datetime(2024, 1, 31, tzinfo=timezone.utc)
    results = service.query_images("ALPHA", start, end)
    ids = [r.image_id for r in results]
    assert r1.image_id in ids
    assert r2.image_id not in ids


def test_query_images_spatial(service):
    r1 = alpha_record("001", TS_JAN)
    r2 = alpha_record("002", TS_JAN)
    service.ingest_images([r1, r2])

    service.ingest_provenance([geo_envelope(r1.image_id, lat=41.5, lon=-70.5)])
    service.ingest_provenance([geo_envelope(r2.image_id, lat=35.0, lon=-20.0)])

    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    end = datetime(2024, 1, 31, tzinfo=timezone.utc)
    results = service.query_images(
        "ALPHA", start, end, lat_min=40.0, lat_max=42.0, lon_min=-72.0, lon_max=-70.0
    )
    ids = [r.image_id for r in results]
    assert r1.image_id in ids
    assert r2.image_id not in ids


# ---------------------------------------------------------------------------
# Sample-scoped
# ---------------------------------------------------------------------------

def test_get_sample_images(service, session):
    register_instrument(session, "ALPHA", "TestCam", DEPLOY_START)
    register_sample(
        session, "SAMPLE_001", "ALPHA",
        datetime(2024, 1, 15, 12, 0, tzinfo=timezone.utc),
        datetime(2024, 1, 15, 12, 10, tzinfo=timezone.utc),
    )
    session.commit()

    r1 = alpha_record("001", TS_JAN)
    r2 = alpha_record("002", TS_FEB)  # outside sample window
    service.ingest_images([r1, r2])

    images = service.get_sample_images("SAMPLE_001")
    ids = [img.image_id for img in images]
    assert r1.image_id in ids
    assert r2.image_id not in ids


def test_get_sample_not_found(service):
    assert service.get_sample("NONEXISTENT") is None


def test_get_sample_images_no_sample(service):
    assert service.get_sample_images("NONEXISTENT") == []


# ---------------------------------------------------------------------------
# Dataset-scoped
# ---------------------------------------------------------------------------

def test_get_dataset_images(service, session):
    ts1 = datetime(2024, 1, 1, tzinfo=timezone.utc)
    ts2 = datetime(2024, 1, 31, tzinfo=timezone.utc)
    add_dataset_span(session, "JAN_DATASET", "ALPHA", ts1, ts2)
    session.commit()

    r1 = alpha_record("001", TS_JAN)
    r2 = alpha_record("002", TS_FEB)
    service.ingest_images([r1, r2])

    images = list(service.get_dataset_images("JAN_DATASET"))
    ids = [img.image_id for img in images]
    assert r1.image_id in ids
    assert r2.image_id not in ids


# ---------------------------------------------------------------------------
# Blob key
# ---------------------------------------------------------------------------

def test_get_blob_key(service):
    record = alpha_record("001")
    service.ingest_images([record])

    blob_env = ProvenanceEnvelope(
        image_id=record.image_id,
        kind="blob",
        source="ifcb-features",
        timestamp=TS_JAN,
        data={"object_key": "blobs/ALPHA/20240115/001.png"},
        instrument="ALPHA",
    )
    service.ingest_provenance([blob_env])

    key = service.get_blob_key(record.image_id)
    assert key == "blobs/ALPHA/20240115/001.png"


def test_get_blob_key_none_when_no_blob(service):
    record = alpha_record("001")
    service.ingest_images([record])
    assert service.get_blob_key(record.image_id) is None
