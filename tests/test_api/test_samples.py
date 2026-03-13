"""API tests for sample endpoints."""

from __future__ import annotations

from datetime import datetime, timezone

from improv.oltp.queries import register_instrument, register_sample

DEPLOY_START = datetime(2022, 1, 1, tzinfo=timezone.utc)
TS = datetime(2024, 1, 15, 12, 0, tzinfo=timezone.utc)
IMAGE_ID = "ALPHA_20240115T120000_001"


def setup_sample(client):
    """Register instrument + sample and ingest an image via the service directly."""
    service = client.app.state.service
    session = service._session
    register_instrument(session, "ALPHA", "TestCam", DEPLOY_START)
    register_sample(
        session,
        "SAMPLE_001",
        "ALPHA",
        datetime(2024, 1, 15, 11, 0, tzinfo=timezone.utc),
        datetime(2024, 1, 15, 13, 0, tzinfo=timezone.utc),
    )
    session.commit()

    client.post(
        "/images",
        json=[{"image_id": IMAGE_ID, "timestamp": TS.isoformat(), "instrument": "ALPHA"}],
    )


def test_get_sample_not_found(client):
    resp = client.get("/samples/NONEXISTENT")
    assert resp.status_code == 404


def test_get_sample(client):
    setup_sample(client)
    resp = client.get("/samples/SAMPLE_001")
    assert resp.status_code == 200
    data = resp.json()
    assert data["sample_id"] == "SAMPLE_001"
    assert data["instrument"] == "ALPHA"


def test_get_sample_images(client):
    setup_sample(client)
    resp = client.get("/samples/SAMPLE_001/images")
    assert resp.status_code == 200
    images = resp.json()
    ids = [img["image_id"] for img in images]
    assert IMAGE_ID in ids
