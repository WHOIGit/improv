"""API tests for sample write endpoints (POST /samples, POST /samples/batch)."""

from __future__ import annotations

DEPLOY_START = "2022-01-01T00:00:00Z"
T1 = "2024-01-15T12:00:00Z"
T2 = "2024-01-15T12:30:00Z"


def _register_instrument(client, name="IFCB107"):
    client.post("/instruments", json={"name": name, "type": "IFCB", "deployment_start": DEPLOY_START})


def _sample(sample_id="S001", instrument="IFCB107", **kwargs):
    return {"sample_id": sample_id, "instrument": instrument, "time_start": T1, "time_end": T2, **kwargs}


# ---------------------------------------------------------------------------
# POST /samples
# ---------------------------------------------------------------------------

def test_register_sample(client):
    _register_instrument(client)
    r = client.post("/samples", json=_sample())
    assert r.status_code == 201
    body = r.json()
    assert body["sample_id"] == "S001"
    assert body["instrument"] == "IFCB107"
    assert body["quality_flag"] is None
    assert body["metadata"] == {}


def test_register_sample_with_metadata(client):
    _register_instrument(client)
    r = client.post("/samples", json=_sample(
        quality_flag=1,
        alternate_sample_id="ALT001",
        metadata={"volume_sampled": 5.0, "run_time": 1200},
    ))
    assert r.status_code == 201
    body = r.json()
    assert body["quality_flag"] == 1
    assert body["alternate_sample_id"] == "ALT001"
    assert body["metadata"]["volume_sampled"] == 5.0


def test_register_sample_conflict(client):
    _register_instrument(client)
    client.post("/samples", json=_sample())
    r = client.post("/samples", json=_sample())
    assert r.status_code == 409


def test_registered_sample_retrievable(client):
    _register_instrument(client)
    client.post("/samples", json=_sample())
    r = client.get("/samples/S001")
    assert r.status_code == 200
    assert r.json()["sample_id"] == "S001"


# ---------------------------------------------------------------------------
# POST /samples/batch
# ---------------------------------------------------------------------------

def test_register_samples_batch(client):
    _register_instrument(client)
    r = client.post("/samples/batch", json=[
        _sample("S001"),
        _sample("S002"),
        _sample("S003"),
    ])
    assert r.status_code == 200
    body = r.json()
    assert body["registered"] == 3
    assert body["skipped"] == 0


def test_register_samples_batch_skips_duplicates(client):
    _register_instrument(client)
    client.post("/samples/batch", json=[_sample("S001"), _sample("S002")])
    # Replay with overlap — S001 and S002 already exist, S003 is new
    r = client.post("/samples/batch", json=[
        _sample("S001"),
        _sample("S002"),
        _sample("S003"),
    ])
    assert r.status_code == 200
    body = r.json()
    assert body["registered"] == 1
    assert body["skipped"] == 2


def test_register_samples_batch_empty(client):
    r = client.post("/samples/batch", json=[])
    assert r.status_code == 200
    assert r.json() == {"registered": 0, "skipped": 0}


def test_register_samples_batch_all_duplicates(client):
    _register_instrument(client)
    client.post("/samples/batch", json=[_sample("S001")])
    r = client.post("/samples/batch", json=[_sample("S001")])
    assert r.status_code == 200
    assert r.json() == {"registered": 0, "skipped": 1}


def test_batch_registered_samples_retrievable(client):
    _register_instrument(client)
    client.post("/samples/batch", json=[_sample("S001"), _sample("S002")])
    assert client.get("/samples/S001").status_code == 200
    assert client.get("/samples/S002").status_code == 200
