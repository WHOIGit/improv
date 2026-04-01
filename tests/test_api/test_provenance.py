"""API tests for provenance endpoints."""

from __future__ import annotations

from datetime import datetime, timezone


TS = datetime(2024, 1, 15, 12, 0, tzinfo=timezone.utc)
IMAGE_ID = "ALPHA_20240115T120000_001"


def ingest_image(client):
    client.post(
        "/images/ingest",
        json=[{"image_id": IMAGE_ID, "timestamp": TS.isoformat(), "instrument": "ALPHA"}],
    )


def test_get_provenance_empty(client):
    ingest_image(client)
    resp = client.get(f"/images/{IMAGE_ID}/provenance?instrument=ALPHA")
    assert resp.status_code == 200
    assert resp.json() == []


def test_post_and_get_provenance(client):
    ingest_image(client)

    resp = client.post(
        f"/images/{IMAGE_ID}/provenance?instrument=ALPHA",
        json={
            "kind": "features",
            "source": "test-pipeline",
            "timestamp": TS.isoformat(),
            "data": {"area": 100.0},
        },
    )
    assert resp.status_code == 201

    resp = client.get(f"/images/{IMAGE_ID}/provenance?instrument=ALPHA")
    assert resp.status_code == 200
    records = resp.json()
    assert len(records) == 1
    assert records[0]["kind"] == "features"
    assert records[0]["data"]["area"] == 100.0


def test_get_provenance_by_kind(client):
    ingest_image(client)

    payloads = {
        "features": {"area": 100.0},
        "geolocation": {
            "lat": 41.5, "lon": -70.5,
            "source": "nav_v1", "version": "1.0",
            "computed_at": TS.isoformat(),
        },
    }
    for kind, data in payloads.items():
        client.post(
            f"/images/{IMAGE_ID}/provenance?instrument=ALPHA",
            json={
                "kind": kind,
                "source": "test",
                "timestamp": TS.isoformat(),
                "data": data,
            },
        )

    resp = client.get(f"/images/{IMAGE_ID}/provenance/features?instrument=ALPHA")
    assert resp.status_code == 200
    records = resp.json()
    assert all(r["kind"] == "features" for r in records)
