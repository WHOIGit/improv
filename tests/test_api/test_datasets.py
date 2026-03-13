"""API tests for dataset endpoints."""

from __future__ import annotations

from datetime import datetime, timezone

T1 = datetime(2024, 1, 1, tzinfo=timezone.utc).isoformat()
T2 = datetime(2024, 6, 30, tzinfo=timezone.utc).isoformat()
T3 = datetime(2024, 7, 1, tzinfo=timezone.utc).isoformat()
T4 = datetime(2024, 12, 31, tzinfo=timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# POST /datasets
# ---------------------------------------------------------------------------

def test_create_dataset(client):
    r = client.post("/datasets", json={"name": "DS1", "description": "Test dataset"})
    assert r.status_code == 201
    body = r.json()
    assert body["name"] == "DS1"
    assert body["description"] == "Test dataset"
    assert body["spans"] == []


def test_create_dataset_no_description(client):
    r = client.post("/datasets", json={"name": "DS1"})
    assert r.status_code == 201
    assert r.json()["description"] is None


def test_create_dataset_conflict(client):
    client.post("/datasets", json={"name": "DS1"})
    r = client.post("/datasets", json={"name": "DS1"})
    assert r.status_code == 409


# ---------------------------------------------------------------------------
# GET /datasets
# ---------------------------------------------------------------------------

def test_list_datasets_empty(client):
    r = client.get("/datasets")
    assert r.status_code == 200
    assert r.json() == []


def test_list_datasets(client):
    client.post("/datasets", json={"name": "DS1"})
    client.post("/datasets", json={"name": "DS2"})
    r = client.get("/datasets")
    assert r.status_code == 200
    names = {d["name"] for d in r.json()}
    assert names == {"DS1", "DS2"}


# ---------------------------------------------------------------------------
# GET /datasets/{name}
# ---------------------------------------------------------------------------

def test_get_dataset(client):
    client.post("/datasets", json={"name": "DS1", "description": "My dataset"})
    r = client.get("/datasets/DS1")
    assert r.status_code == 200
    body = r.json()
    assert body["name"] == "DS1"
    assert body["description"] == "My dataset"
    assert body["spans"] == []


def test_get_dataset_not_found(client):
    r = client.get("/datasets/MISSING")
    assert r.status_code == 404


def test_get_dataset_includes_spans(client):
    client.post("/datasets", json={"name": "DS1"})
    client.post("/datasets/DS1/spans", json=[
        {"instrument": "IFCB107", "time_start": T1, "time_end": T2},
    ])
    r = client.get("/datasets/DS1")
    assert r.status_code == 200
    spans = r.json()["spans"]
    assert len(spans) == 1
    assert spans[0]["instrument"] == "IFCB107"


# ---------------------------------------------------------------------------
# POST /datasets/{name}/spans
# ---------------------------------------------------------------------------

def test_add_spans(client):
    client.post("/datasets", json={"name": "DS1"})
    r = client.post("/datasets/DS1/spans", json=[
        {"instrument": "IFCB107", "time_start": T1, "time_end": T2},
        {"instrument": "IFCB108", "time_start": T3, "time_end": T4},
    ])
    assert r.status_code == 201
    spans = r.json()
    assert len(spans) == 2
    instruments = {s["instrument"] for s in spans}
    assert instruments == {"IFCB107", "IFCB108"}


def test_add_spans_returns_span_ids(client):
    client.post("/datasets", json={"name": "DS1"})
    r = client.post("/datasets/DS1/spans", json=[
        {"instrument": "IFCB107", "time_start": T1, "time_end": T2},
    ])
    assert r.status_code == 201
    span = r.json()[0]
    assert "span_id" in span
    assert span["span_id"]  # non-empty


def test_add_spans_dataset_not_found(client):
    r = client.post("/datasets/MISSING/spans", json=[
        {"instrument": "IFCB107", "time_start": T1, "time_end": T2},
    ])
    assert r.status_code == 404


def test_add_spans_accumulate(client):
    """Spans posted in separate requests both appear in GET."""
    client.post("/datasets", json={"name": "DS1"})
    client.post("/datasets/DS1/spans", json=[
        {"instrument": "IFCB107", "time_start": T1, "time_end": T2},
    ])
    client.post("/datasets/DS1/spans", json=[
        {"instrument": "IFCB108", "time_start": T3, "time_end": T4},
    ])
    r = client.get("/datasets/DS1")
    assert len(r.json()["spans"]) == 2
