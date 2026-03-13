"""Tests for built-in plugins."""

from __future__ import annotations

from datetime import datetime, timezone

from improv.models.provenance import ProvenanceEnvelope
from improv.plugins.geolocation import GeoLocationIndexRecord, GeoLocationPlugin
from improv.plugins.sample_context import SampleContextPlugin, SampleIndexRecord


def make_env(kind: str, data: dict, instrument="ALPHA", year=2024, month=1):
    return ProvenanceEnvelope(
        image_id="ALPHA_20240115T120000_001",
        kind=kind,
        source="test",
        timestamp=datetime(2024, 1, 15, 12, 0, tzinfo=timezone.utc),
        data=data,
        instrument=instrument,
        year=year,
        month=month,
    )


# ---------------------------------------------------------------------------
# GeoLocationPlugin
# ---------------------------------------------------------------------------

def test_geolocation_index_record_model():
    r = GeoLocationIndexRecord(
        image_id="img1",
        lat=41.5,
        lon=-70.5,
        source="nav_v1",
        version="1.0",
        computed_at=datetime(2024, 1, 15, 12, 0, tzinfo=timezone.utc),
    )
    assert r.depth is None
    assert r.instrument is None


def test_geolocation_plugin_extract():
    plugin = GeoLocationPlugin()
    env = make_env(
        "geolocation",
        {
            "lat": 41.5,
            "lon": -70.5,
            "depth": 5.0,
            "source": "nav_v1",
            "version": "1.0",
            "computed_at": "2024-01-15T12:00:00+00:00",
        },
    )
    record = plugin.extract_index_record(env)
    assert record is not None
    assert record["lat"] == 41.5
    assert record["lon"] == -70.5
    assert record["depth"] == 5.0
    assert record["instrument"] == "ALPHA"
    assert record["year"] == 2024
    assert record["month"] == 1


def test_geolocation_plugin_extract_no_depth():
    plugin = GeoLocationPlugin()
    env = make_env(
        "geolocation",
        {
            "lat": 41.0,
            "lon": -70.0,
            "source": "nav_v1",
            "version": "1.0",
            "computed_at": "2024-01-15T12:00:00+00:00",
        },
    )
    record = plugin.extract_index_record(env)
    assert record["depth"] is None


def test_geolocation_plugin_creates_table(store):
    plugin = GeoLocationPlugin()
    plugin.create_index(store)
    # idempotent
    plugin.create_index(store)


# ---------------------------------------------------------------------------
# SampleContextPlugin
# ---------------------------------------------------------------------------

def test_sample_index_record_model():
    r = SampleIndexRecord(
        image_id="img1",
        sample_id="SAMPLE_001",
        source="ifcb_system",
    )
    assert r.instrument is None


def test_sample_context_plugin_extract():
    plugin = SampleContextPlugin()
    env = make_env(
        "sample_context",
        {"sample_id": "SAMPLE_001", "source": "ifcb_system"},
    )
    record = plugin.extract_index_record(env)
    assert record is not None
    assert record["sample_id"] == "SAMPLE_001"
    assert record["source"] == "ifcb_system"
    assert record["instrument"] == "ALPHA"


def test_sample_context_plugin_creates_table(store):
    plugin = SampleContextPlugin()
    plugin.create_index(store)
    plugin.create_index(store)  # idempotent
