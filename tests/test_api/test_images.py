"""API tests for image endpoints."""

from __future__ import annotations

from datetime import datetime, timezone

from improv.models.image import ImageRecord
from improv.store.images import write_images


TS = datetime(2024, 1, 15, 12, 0, tzinfo=timezone.utc)


def ingest_image(client, image_id: str, ts: datetime = TS):
    return client.post(
        "/images/ingest",
        json=[{"image_id": image_id, "timestamp": ts.isoformat(), "instrument": "ALPHA"}],
    )


def test_get_image_metadata_not_found(client):
    resp = client.get("/images/ALPHA_20240115T120000_999/metadata?instrument=ALPHA")
    assert resp.status_code == 404


def test_ingest_and_get_image_metadata(client):
    image_id = "ALPHA_20240115T120000_001"
    resp = ingest_image(client, image_id)
    assert resp.status_code == 201
    assert resp.json()["ingested"] == 1

    resp = client.get(f"/images/{image_id}/metadata")
    assert resp.status_code == 200
    data = resp.json()
    assert data["image_id"] == image_id
    assert data["instrument"] == "ALPHA"


def test_search_images_time_range(client):
    ingest_image(client, "ALPHA_20240115T120000_001")
    ingest_image(client, "ALPHA_20240215T120000_002", datetime(2024, 2, 15, 12, 0, tzinfo=timezone.utc))

    resp = client.get(
        "/images/search",
        params={
            "instrument": "ALPHA",
            "time_start": "2024-01-01T00:00:00Z",
            "time_end": "2024-01-31T23:59:59Z",
        },
    )
    assert resp.status_code == 200
    ids = [r["image_id"] for r in resp.json()]
    assert "ALPHA_20240115T120000_001" in ids
    assert "ALPHA_20240215T120000_002" not in ids


def test_search_images_missing_params(client):
    resp = client.get("/images/search", params={"instrument": "ALPHA"})
    assert resp.status_code == 400
