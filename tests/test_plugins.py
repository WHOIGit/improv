"""Tests for built-in plugins."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from improv.models.provenance import ProvenanceEnvelope
from improv.plugins.classification import (
    MachineClassificationIndexRecord,
    MachineClassificationPlugin,
)
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


# ---------------------------------------------------------------------------
# MachineClassificationPlugin (generic, any classifier)
# ---------------------------------------------------------------------------

def test_classification_plugin_parameterized():
    plugin = MachineClassificationPlugin(
        kind="ecotaxa_cnn", index_table="ecotaxa_cnn_index"
    )
    assert plugin.kind == "ecotaxa_cnn"
    assert plugin.index_table == "ecotaxa_cnn_index"
    assert plugin.index_schema is MachineClassificationIndexRecord
    assert "model_version" in plugin.partition_by


def test_classification_plugin_extract_narrow_index():
    """Non-IFCB classifier: index carries winner_index only, no names/scores."""
    plugin = MachineClassificationPlugin(
        kind="ecotaxa_cnn", index_table="ecotaxa_cnn_index"
    )
    env = make_env(
        "ecotaxa_cnn",
        {
            "run_id": "run-1",
            "model_version": "ecotaxa-cnn-v4",
            "scores": [0.9, 0.1],
            "winner_index": 0,
            "winner_score": 0.9,
        },
    )
    record = plugin.extract_index_record(env)
    assert record is not None
    assert record["winner_index"] == 0
    assert record["winner_score"] == 0.9
    assert record["run_id"] == "run-1"
    assert record["instrument"] == "ALPHA"
    assert record["year"] == 2024
    # positional score vector and names are NOT indexed
    assert "scores" not in record
    assert "winner" not in record


def test_classification_plugin_winner_index_out_of_range():
    plugin = MachineClassificationPlugin(kind="ecotaxa_cnn")
    env = make_env(
        "ecotaxa_cnn",
        {
            "run_id": "run-1",
            "model_version": "v1",
            "scores": [0.9, 0.1],
            "winner_index": 2,   # out of range
            "winner_score": 0.9,
        },
    )
    with pytest.raises(ValueError):
        plugin.extract_index_record(env)


def test_classification_plugin_creates_table(store):
    plugin = MachineClassificationPlugin(
        kind="ecotaxa_cnn", index_table="ecotaxa_cnn_index"
    )
    plugin.create_index(store)
    plugin.create_index(store)  # idempotent


def test_ifcb_cnn_preset_backcompat():
    from improv.plugins.ifcb import (
        IFCBCNNClassificationIndexRecord,
        IFCBCNNClassificationPlugin,
    )
    plugin = IFCBCNNClassificationPlugin()
    assert plugin.kind == "ifcb_cnn_classification"
    assert plugin.index_table == "ifcb_cnn_classification_index"
    assert IFCBCNNClassificationIndexRecord is MachineClassificationIndexRecord
    assert isinstance(plugin, MachineClassificationPlugin)
