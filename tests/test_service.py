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

    from improv.plugins.geolocation import GeoLocationPlugin
    ids = GeoLocationPlugin().query_spatial(store_with_tables, 41.0, 42.0, -71.0, -70.0)
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
# Classifier taxonomy (label-map)
# ---------------------------------------------------------------------------

def test_register_classifier_taxonomy_idempotent(service):
    tax, created = service.register_classifier_taxonomy(
        "ifcb_cnn_classification", "v4", ["Ceratium", "Chaetoceros"]
    )
    assert created is True
    assert tax.class_names == ["Ceratium", "Chaetoceros"]

    again, created2 = service.register_classifier_taxonomy(
        "ifcb_cnn_classification", "v4", ["ignored"]
    )
    assert created2 is False
    assert again.taxonomy_id == tax.taxonomy_id
    assert again.class_names == ["Ceratium", "Chaetoceros"]  # unchanged


def test_get_classifier_taxonomy_exact_version(service):
    service.register_classifier_taxonomy("clf", "v1", ["A", "B"])
    service.register_classifier_taxonomy("clf", "v2", ["A", "B", "C"])

    v1 = service.get_classifier_taxonomy("clf", "v1")
    v2 = service.get_classifier_taxonomy("clf", "v2")
    assert v1.class_names == ["A", "B"]
    assert v2.class_names == ["A", "B", "C"]
    assert service.get_classifier_taxonomy("clf", "missing") is None


def test_get_latest_classifier_taxonomy(service):
    service.register_classifier_taxonomy("clf", "v1", ["A"])
    service.register_classifier_taxonomy("clf", "v2", ["A", "B"])
    latest = service.get_latest_classifier_taxonomy("clf")
    assert latest.model_version == "v2"


def test_decode_classification_roundtrip(service):
    service.register_classifier_taxonomy(
        "ifcb_cnn_classification", "v4", ["Ceratium", "Chaetoceros", "Dinophysis"]
    )
    decoded = service.decode_classification(
        "ifcb_cnn_classification", "v4", [0.1, 0.7, 0.2], winner_index=1
    )
    assert decoded["winner"] == "Chaetoceros"
    assert decoded["scores"] == {"Ceratium": 0.1, "Chaetoceros": 0.7, "Dinophysis": 0.2}


def test_decode_classification_unknown_version(service):
    with pytest.raises(ValueError):
        service.decode_classification("clf", "nope", [0.5, 0.5], winner_index=0)


def test_decode_classification_length_mismatch(service):
    service.register_classifier_taxonomy("clf", "v1", ["A", "B"])
    with pytest.raises(ValueError):
        service.decode_classification("clf", "v1", [0.5, 0.3, 0.2], winner_index=0)


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


def test_batch_provenance_writes_one_index_call_per_table(service, monkeypatch):
    """A batch of N same-kind records → one batched index write, not N."""
    recs = [alpha_record(f"00{i}") for i in range(1, 4)]
    service.ingest_images(recs)
    envs = [
        geo_envelope(r.image_id, lat=41.0 + i * 0.1, lon=-70.0)
        for i, r in enumerate(recs)
    ]

    calls: list[tuple[str, int]] = []
    orig = service._store.write

    def spy(table, records, *args, **kwargs):
        calls.append((table, len(records)))
        return orig(table, records, *args, **kwargs)

    monkeypatch.setattr(service._store, "write", spy)
    service.ingest_provenance(envs)

    assert ("provenance", 3) in calls
    # geolocation_index written once with all 3 rows, not three single-row writes
    assert [c for c in calls if c[0] == "geolocation_index"] == [("geolocation_index", 3)]
