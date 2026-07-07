"""Tests for the thin HTTP ingest client."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from improv.client import ImprovClient


DEPLOY_START = datetime(2022, 1, 1, tzinfo=timezone.utc)
TS_START = datetime(2024, 1, 15, 12, 0, tzinfo=timezone.utc)
TS_END = datetime(2024, 1, 15, 12, 30, tzinfo=timezone.utc)


@pytest.fixture
def improv_client(client):
    """Wrap the FastAPI TestClient in an ImprovClient."""
    return ImprovClient(base_url="http://testserver", _client=client)


# ------------------------------------------------------------------
# Instruments
# ------------------------------------------------------------------


def test_register_instrument(improv_client):
    instrument, created = improv_client.register_instrument(
        name="ALPHA",
        type="TestCam",
        deployment_start=DEPLOY_START,
        serial_number="001",
    )
    assert created is True
    assert instrument["name"] == "ALPHA"
    assert instrument["type"] == "TestCam"
    assert instrument["serial_number"] == "001"


def test_register_instrument_idempotent(improv_client):
    improv_client.register_instrument(
        name="ALPHA",
        type="TestCam",
        deployment_start=DEPLOY_START,
    )
    instrument, created = improv_client.register_instrument(
        name="ALPHA",
        type="TestCam",
        deployment_start=DEPLOY_START,
    )
    assert created is False
    assert instrument["name"] == "ALPHA"


def test_get_instrument(improv_client):
    improv_client.register_instrument(
        name="ALPHA",
        type="TestCam",
        deployment_start=DEPLOY_START,
    )
    instrument = improv_client.get_instrument("ALPHA")
    assert instrument is not None
    assert instrument["name"] == "ALPHA"


def test_get_instrument_not_found(improv_client):
    assert improv_client.get_instrument("NONEXISTENT") is None


# ------------------------------------------------------------------
# Samples
# ------------------------------------------------------------------


def test_register_sample(improv_client):
    improv_client.register_instrument(
        name="ALPHA",
        type="TestCam",
        deployment_start=DEPLOY_START,
    )
    sample, created = improv_client.register_sample(
        sample_id="BIN_001",
        instrument="ALPHA",
        time_start=TS_START,
        time_end=TS_END,
        metadata={"volume_ml": 5.0},
    )
    assert created is True
    assert sample["sample_id"] == "BIN_001"
    assert sample["instrument"] == "ALPHA"
    assert sample["metadata"]["volume_ml"] == 5.0


def test_register_sample_idempotent(improv_client):
    improv_client.register_instrument(
        name="ALPHA",
        type="TestCam",
        deployment_start=DEPLOY_START,
    )
    improv_client.register_sample(
        sample_id="BIN_001",
        instrument="ALPHA",
        time_start=TS_START,
        time_end=TS_END,
    )
    sample, created = improv_client.register_sample(
        sample_id="BIN_001",
        instrument="ALPHA",
        time_start=TS_START,
        time_end=TS_END,
    )
    assert created is False
    assert sample["sample_id"] == "BIN_001"


def test_get_sample(improv_client):
    improv_client.register_instrument(
        name="ALPHA",
        type="TestCam",
        deployment_start=DEPLOY_START,
    )
    improv_client.register_sample(
        sample_id="BIN_001",
        instrument="ALPHA",
        time_start=TS_START,
        time_end=TS_END,
    )
    sample = improv_client.get_sample("BIN_001")
    assert sample is not None
    assert sample["sample_id"] == "BIN_001"


def test_get_sample_not_found(improv_client):
    assert improv_client.get_sample("NONEXISTENT") is None


def test_register_samples_batch(improv_client):
    improv_client.register_instrument(
        name="ALPHA",
        type="TestCam",
        deployment_start=DEPLOY_START,
    )
    samples = [
        {
            "sample_id": f"BIN_{i:03d}",
            "instrument": "ALPHA",
            "time_start": TS_START.isoformat(),
            "time_end": TS_END.isoformat(),
        }
        for i in range(1, 4)
    ]
    registered, skipped = improv_client.register_samples_batch(samples)
    assert registered == 3
    assert skipped == 0

    # Re-register — all should be skipped
    registered, skipped = improv_client.register_samples_batch(samples)
    assert registered == 0
    assert skipped == 3


# ------------------------------------------------------------------
# Ingest Tasks
# ------------------------------------------------------------------


def test_register_ingest_task(improv_client):
    task, created = improv_client.register_ingest_task(
        task_id="D20240115T120000_IFCB014",
        instrument="ALPHA",
    )
    assert created is True
    assert task["task_id"] == "D20240115T120000_IFCB014"
    assert task["instrument"] == "ALPHA"
    assert task["status"] == "pending"


def test_register_ingest_task_idempotent(improv_client):
    improv_client.register_ingest_task(
        task_id="D20240115T120000_IFCB014",
        instrument="ALPHA",
    )
    task, created = improv_client.register_ingest_task(
        task_id="D20240115T120000_IFCB014",
        instrument="ALPHA",
    )
    assert created is False
    assert task["task_id"] == "D20240115T120000_IFCB014"


def test_complete_ingest_task(improv_client):
    improv_client.register_ingest_task(
        task_id="D20240115T120000_IFCB014",
        instrument="ALPHA",
    )
    task = improv_client.complete_ingest_task("D20240115T120000_IFCB014")
    assert task["status"] == "complete"
    assert task["updated_at"] is not None


def test_fail_ingest_task(improv_client):
    improv_client.register_ingest_task(
        task_id="D20240115T120000_IFCB014",
        instrument="ALPHA",
    )
    task = improv_client.fail_ingest_task("D20240115T120000_IFCB014")
    assert task["status"] == "failed"
    assert task["updated_at"] is not None


def test_pending_heartbeat(improv_client):
    task, _ = improv_client.register_ingest_task(
        task_id="D20240115T120000_IFCB014",
        instrument="ALPHA",
    )
    original_updated = task["updated_at"]
    updated = improv_client.update_ingest_task("D20240115T120000_IFCB014", "pending")
    assert updated["status"] == "pending"
    assert updated["updated_at"] >= original_updated


def test_delete_ingest_task(improv_client):
    improv_client.register_ingest_task(
        task_id="D20240115T120000_IFCB014",
        instrument="ALPHA",
    )
    assert improv_client.delete_ingest_task("D20240115T120000_IFCB014") is True
    assert improv_client.get_ingest_task("D20240115T120000_IFCB014") is None


def test_delete_ingest_task_not_found(improv_client):
    assert improv_client.delete_ingest_task("NONEXISTENT") is False


def test_delete_and_reregister(improv_client):
    improv_client.register_ingest_task(
        task_id="D20240115T120000_IFCB014",
        instrument="ALPHA",
    )
    improv_client.fail_ingest_task("D20240115T120000_IFCB014")
    improv_client.delete_ingest_task("D20240115T120000_IFCB014")
    task, created = improv_client.register_ingest_task(
        task_id="D20240115T120000_IFCB014",
        instrument="ALPHA",
    )
    assert created is True
    assert task["status"] == "pending"


def test_get_ingest_task(improv_client):
    improv_client.register_ingest_task(
        task_id="D20240115T120000_IFCB014",
        instrument="ALPHA",
    )
    task = improv_client.get_ingest_task("D20240115T120000_IFCB014")
    assert task is not None
    assert task["status"] == "pending"


def test_get_ingest_task_not_found(improv_client):
    assert improv_client.get_ingest_task("NONEXISTENT") is None


# ------------------------------------------------------------------
# Classifier taxonomy
# ------------------------------------------------------------------

CLASSIFIER = "ifcb_cnn_classification"


def test_register_classifier_taxonomy(improv_client):
    taxonomy, created = improv_client.register_classifier_taxonomy(
        CLASSIFIER, "v4", ["Ceratium", "Chaetoceros"]
    )
    assert created is True
    assert taxonomy["classifier"] == CLASSIFIER
    assert taxonomy["model_version"] == "v4"
    assert taxonomy["class_names"] == ["Ceratium", "Chaetoceros"]


def test_register_classifier_taxonomy_idempotent(improv_client):
    improv_client.register_classifier_taxonomy(CLASSIFIER, "v4", ["A", "B"])
    taxonomy, created = improv_client.register_classifier_taxonomy(
        CLASSIFIER, "v4", ["A", "B"]
    )
    assert created is False
    assert taxonomy["class_names"] == ["A", "B"]


def test_get_classifier_taxonomy(improv_client):
    improv_client.register_classifier_taxonomy(CLASSIFIER, "v4", ["A", "B", "C"])
    taxonomy = improv_client.get_classifier_taxonomy(CLASSIFIER, "v4")
    assert taxonomy is not None
    assert taxonomy["class_names"] == ["A", "B", "C"]


def test_get_classifier_taxonomy_not_found(improv_client):
    assert improv_client.get_classifier_taxonomy(CLASSIFIER, "nope") is None
