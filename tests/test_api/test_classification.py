"""API tests for classifier taxonomy + classification-decode endpoints."""

from __future__ import annotations

from datetime import datetime, timezone


TS = datetime(2024, 1, 15, 12, 0, tzinfo=timezone.utc)
IMAGE_ID = "ALPHA_20240115T120000_001"
CLASSIFIER = "ifcb_cnn_classification"


def _register(client, model_version, class_names):
    return client.post(
        f"/classifiers/{CLASSIFIER}/taxonomies",
        json={"model_version": model_version, "class_names": class_names},
    )


def _ingest_classification(client, model_version, scores, winner_index):
    client.post(
        "/images/ingest",
        json=[{"image_id": IMAGE_ID, "timestamp": TS.isoformat(), "instrument": "ALPHA"}],
    )
    return client.post(
        f"/images/{IMAGE_ID}/provenance?instrument=ALPHA",
        json={
            "kind": CLASSIFIER,
            "source": "test-classifier",
            "timestamp": TS.isoformat(),
            "data": {
                "run_id": "run-1",
                "model_version": model_version,
                "scores": scores,
                "winner_index": winner_index,
                "winner_score": scores[winner_index],
            },
        },
    )


# ---------------------------------------------------------------------------
# Taxonomy registration + lookup
# ---------------------------------------------------------------------------

def test_register_taxonomy(client):
    resp = _register(client, "v4", ["Ceratium", "Chaetoceros", "Dinophysis"])
    assert resp.status_code == 201
    body = resp.json()
    assert body["classifier"] == CLASSIFIER
    assert body["model_version"] == "v4"
    assert body["class_names"] == ["Ceratium", "Chaetoceros", "Dinophysis"]


def test_register_taxonomy_idempotent(client):
    _register(client, "v4", ["A", "B"])
    resp = _register(client, "v4", ["A", "B"])
    assert resp.status_code == 409
    # Still exactly one row, unchanged.
    got = client.get(f"/classifiers/{CLASSIFIER}/taxonomies/v4").json()
    assert got["class_names"] == ["A", "B"]


def test_get_taxonomy_by_version(client):
    _register(client, "v4", ["Ceratium", "Chaetoceros"])
    resp = client.get(f"/classifiers/{CLASSIFIER}/taxonomies/v4")
    assert resp.status_code == 200
    assert resp.json()["class_names"] == ["Ceratium", "Chaetoceros"]


def test_get_taxonomy_unknown_version(client):
    resp = client.get(f"/classifiers/{CLASSIFIER}/taxonomies/nope")
    assert resp.status_code == 404


def test_get_latest_taxonomy(client):
    _register(client, "v1", ["A"])
    _register(client, "v2", ["A", "B"])
    resp = client.get(f"/classifiers/{CLASSIFIER}/taxonomies/latest")
    assert resp.status_code == 200
    assert resp.json()["model_version"] == "v2"


def test_get_latest_taxonomy_none(client):
    resp = client.get(f"/classifiers/{CLASSIFIER}/taxonomies/latest")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# (A) stateless decode
# ---------------------------------------------------------------------------

def test_decode(client):
    _register(client, "v4", ["Ceratium", "Chaetoceros", "Dinophysis"])
    resp = client.post(
        f"/classifiers/{CLASSIFIER}/decode",
        json={"model_version": "v4", "scores": [0.1, 0.7, 0.2], "winner_index": 1},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["winner"] == "Chaetoceros"
    assert body["scores"] == {"Ceratium": 0.1, "Chaetoceros": 0.7, "Dinophysis": 0.2}


def test_decode_length_mismatch(client):
    _register(client, "v4", ["A", "B", "C"])
    resp = client.post(
        f"/classifiers/{CLASSIFIER}/decode",
        json={"model_version": "v4", "scores": [0.5, 0.5], "winner_index": 0},
    )
    assert resp.status_code == 422


def test_decode_unknown_taxonomy(client):
    resp = client.post(
        f"/classifiers/{CLASSIFIER}/decode",
        json={"model_version": "v4", "scores": [0.5, 0.5], "winner_index": 0},
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# (B) decoded classification read
# ---------------------------------------------------------------------------

def test_decoded_classification_read(client):
    _register(client, "v4", ["Ceratium", "Chaetoceros", "Dinophysis"])
    _ingest_classification(client, "v4", [0.1, 0.7, 0.2], winner_index=1)

    resp = client.get(
        f"/images/{IMAGE_ID}/classification?kind={CLASSIFIER}&instrument=ALPHA"
    )
    assert resp.status_code == 200
    records = resp.json()
    assert len(records) == 1
    assert records[0]["winner"] == "Chaetoceros"
    assert records[0]["scores"]["Chaetoceros"] == 0.7


def test_decoded_read_uses_records_own_version(client):
    # Two versions with DIFFERENT orderings. Each stored record must decode
    # against its own model_version, not "latest".
    _register(client, "v1", ["Ceratium", "Chaetoceros"])
    _register(client, "v2", ["Chaetoceros", "Ceratium"])  # reversed order

    client.post(
        "/images/ingest",
        json=[{"image_id": IMAGE_ID, "timestamp": TS.isoformat(), "instrument": "ALPHA"}],
    )
    # winner_index=0 under each version → different names because orderings differ.
    for mv in ("v1", "v2"):
        client.post(
            f"/images/{IMAGE_ID}/provenance?instrument=ALPHA",
            json={
                "kind": CLASSIFIER,
                "source": "test",
                "timestamp": TS.isoformat(),
                "data": {
                    "run_id": f"run-{mv}",
                    "model_version": mv,
                    "scores": [0.9, 0.1],
                    "winner_index": 0,
                    "winner_score": 0.9,
                },
            },
        )

    records = client.get(
        f"/images/{IMAGE_ID}/classification?kind={CLASSIFIER}&instrument=ALPHA"
    ).json()
    winners = {r["winner"] for r in records}
    # v1[0]=Ceratium, v2[0]=Chaetoceros — proves per-record decoding, not latest.
    assert winners == {"Ceratium", "Chaetoceros"}
