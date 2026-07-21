"""Tests for store/provenance.py."""

from __future__ import annotations

from datetime import datetime, timezone

from improv.models.provenance import ProvenanceEnvelope
from improv.store.provenance import (
    get_provenance,
    get_provenance_by_kind,
    write_provenance,
)


def make_envelope(
    image_id: str,
    kind: str,
    data: dict,
    ts: datetime | None = None,
    instrument: str = "ALPHA",
) -> ProvenanceEnvelope:
    ts = ts or datetime(2024, 1, 15, 12, 0, tzinfo=timezone.utc)
    return ProvenanceEnvelope(
        image_id=image_id,
        kind=kind,
        source="test_source",
        timestamp=ts,
        data=data,
        instrument=instrument,
    )


def test_write_and_read_round_trip(store_with_tables, parsers):
    env = make_envelope("ALPHA_20240115T120000_001", "geolocation", {"lat": 41.5})
    write_provenance(store_with_tables, [env], parsers)

    results = get_provenance(
        store_with_tables, "ALPHA_20240115T120000_001", parsers
    )
    assert len(results) == 1
    assert results[0].kind == "geolocation"
    assert results[0].data["lat"] == 41.5


def test_data_json_round_trip(store_with_tables, parsers):
    """dict data survives the JSON string round-trip through the columnar store."""
    data = {"nested": {"key": "value"}, "list": [1, 2, 3], "float": 3.14}
    env = make_envelope("ALPHA_20240115T120000_001", "features", data)
    write_provenance(store_with_tables, [env], parsers)

    results = get_provenance(
        store_with_tables, "ALPHA_20240115T120000_001", parsers
    )
    assert results[0].data == data


def test_kind_filter(store_with_tables, parsers):
    image_id = "ALPHA_20240115T120000_001"
    write_provenance(
        store_with_tables,
        [
            make_envelope(image_id, "geolocation", {"lat": 41.5}),
            make_envelope(image_id, "features", {"area": 100.0}),
        ],
        parsers,
    )

    geo = get_provenance_by_kind(store_with_tables, image_id, "geolocation", parsers)
    assert len(geo) == 1
    assert geo[0].kind == "geolocation"

    feats = get_provenance_by_kind(store_with_tables, image_id, "features", parsers)
    assert len(feats) == 1
    assert feats[0].kind == "features"


def test_append_only_multiple_records(store_with_tables, parsers):
    """Multiple provenance records for the same image accumulate."""
    image_id = "ALPHA_20240115T120000_001"
    for i in range(3):
        env = make_envelope(image_id, "geolocation", {"version": i})
        write_provenance(store_with_tables, [env], parsers)

    results = get_provenance(store_with_tables, image_id, parsers)
    assert len(results) == 3


def test_not_found_returns_empty(store_with_tables, parsers):
    results = get_provenance(
        store_with_tables, "ALPHA_20240115T120000_999", parsers
    )
    assert results == []


def test_retry_same_record_is_idempotent(store_with_tables, parsers):
    """Re-writing an identical record collapses at read time (retry safety)."""
    image_id = "ALPHA_20240115T120000_001"
    env = make_envelope(image_id, "geolocation", {"lat": 41.5, "lon": -70.0})
    write_provenance(store_with_tables, [env], parsers)
    write_provenance(store_with_tables, [env], parsers)  # retry

    results = get_provenance(store_with_tables, image_id, parsers)
    assert len(results) == 1
    assert results[0].data == {"lat": 41.5, "lon": -70.0}


def test_distinct_payloads_both_kept(store_with_tables, parsers):
    """Same (image_id, kind, source) but different data are distinct facts."""
    image_id = "ALPHA_20240115T120000_001"
    write_provenance(
        store_with_tables,
        [make_envelope(image_id, "classification", {"model": "cnn_v1", "score": 0.9})],
        parsers,
    )
    write_provenance(
        store_with_tables,
        [make_envelope(image_id, "classification", {"model": "cnn_v2", "score": 0.8})],
        parsers,
    )

    results = get_provenance_by_kind(store_with_tables, image_id, "classification", parsers)
    assert len(results) == 2


def test_dedup_is_key_order_insensitive(store_with_tables, parsers):
    """Canonical (JCS) hashing dedups payloads that differ only in key order."""
    image_id = "ALPHA_20240115T120000_001"
    write_provenance(
        store_with_tables,
        [make_envelope(image_id, "features", {"area": 100.0, "perimeter": 40.0})],
        parsers,
    )
    write_provenance(
        store_with_tables,
        [make_envelope(image_id, "features", {"perimeter": 40.0, "area": 100.0})],
        parsers,
    )

    results = get_provenance(store_with_tables, image_id, parsers)
    assert len(results) == 1


def test_dedup_treats_int_and_float_as_equal(store_with_tables, parsers):
    """JCS number canonicalization: 1 and 1.0 hash identically, so they dedup."""
    image_id = "ALPHA_20240115T120000_001"
    write_provenance(
        store_with_tables,
        [make_envelope(image_id, "features", {"count": 1})],
        parsers,
    )
    write_provenance(
        store_with_tables,
        [make_envelope(image_id, "features", {"count": 1.0})],
        parsers,
    )

    results = get_provenance(store_with_tables, image_id, parsers)
    assert len(results) == 1
