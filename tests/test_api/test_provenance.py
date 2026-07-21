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


def test_provenance_response_includes_year_month(client):
    ingest_image(client)
    client.post(
        f"/images/{IMAGE_ID}/provenance?instrument=ALPHA",
        json={
            "kind": "features",
            "source": "test",
            "timestamp": TS.isoformat(),
            "data": {"area": 100.0},
        },
    )
    records = client.get(f"/images/{IMAGE_ID}/provenance?instrument=ALPHA").json()
    assert records[0]["year"] == TS.year
    assert records[0]["month"] == TS.month


# ---------------------------------------------------------------------------
# Batch ingest
# ---------------------------------------------------------------------------

IMAGE_ID_2 = "ALPHA_20240115T120000_002"


def _batch_record(image_id, area):
    return {
        "image_id": image_id,
        "kind": "features",
        "source": "test-batch",
        "timestamp": TS.isoformat(),
        "data": {"area": area},
    }


def test_batch_single_instrument_roundtrip(client):
    client.post(
        "/images/ingest",
        json=[
            {"image_id": IMAGE_ID, "timestamp": TS.isoformat(), "instrument": "ALPHA"},
            {"image_id": IMAGE_ID_2, "timestamp": TS.isoformat(), "instrument": "ALPHA"},
        ],
    )

    resp = client.post(
        "/images/provenance/batch",
        json={"records": [
            _batch_record(IMAGE_ID, 100.0),
            _batch_record(IMAGE_ID_2, 200.0),
        ]},
    )
    assert resp.status_code == 201
    assert resp.json()["ingested"] == 2

    r1 = client.get(f"/images/{IMAGE_ID}/provenance?instrument=ALPHA").json()
    r2 = client.get(f"/images/{IMAGE_ID_2}/provenance?instrument=ALPHA").json()
    assert r1[0]["data"]["area"] == 100.0
    assert r2[0]["data"]["area"] == 200.0
    # Each record landed under its own image_id, not an empty shared id.
    assert r1[0]["image_id"] == IMAGE_ID
    assert r2[0]["image_id"] == IMAGE_ID_2


def test_batch_multi_instrument_rejected(client):
    resp = client.post(
        "/images/provenance/batch",
        json={"records": [
            _batch_record("ALPHA_20240115T120000_001", 100.0),
            _batch_record("BETA-20240115T120000-001", 200.0),
        ]},
    )
    assert resp.status_code == 422
    # All-or-nothing: nothing written for either record's image_id.
    assert client.get(
        "/images/ALPHA_20240115T120000_001/provenance?instrument=ALPHA"
    ).json() == []
    assert client.get(
        "/images/BETA-20240115T120000-001/provenance?instrument=BETA"
    ).json() == []


def test_batch_unparseable_image_id_uses_instrument_hint(client):
    resp = client.post(
        "/images/provenance/batch?instrument=ALPHA",
        json={"records": [_batch_record("no-parser-match", 100.0)]},
    )
    assert resp.status_code == 201
    records = client.get(
        "/images/no-parser-match/provenance?instrument=ALPHA"
    ).json()
    assert records[0]["data"]["area"] == 100.0
