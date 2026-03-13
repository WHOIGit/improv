"""API tests for instrument endpoints."""

from __future__ import annotations

DEPLOY_START = "2022-01-01T00:00:00Z"


def _instrument(name="IFCB107", **kwargs):
    return {"name": name, "type": "IFCB", "deployment_start": DEPLOY_START, **kwargs}


# ---------------------------------------------------------------------------
# POST /instruments
# ---------------------------------------------------------------------------

def test_register_instrument(client):
    r = client.post("/instruments", json=_instrument())
    assert r.status_code == 201
    body = r.json()
    assert body["name"] == "IFCB107"
    assert body["type"] == "IFCB"
    assert body["serial_number"] is None
    assert body["description"] is None


def test_register_instrument_with_optional_fields(client):
    r = client.post("/instruments", json=_instrument(
        serial_number="SN-123",
        description="Primary MVCO unit",
        deployment_end="2026-12-31T00:00:00Z",
    ))
    assert r.status_code == 201
    body = r.json()
    assert body["serial_number"] == "SN-123"
    assert body["description"] == "Primary MVCO unit"
    assert body["deployment_end"] is not None


def test_register_instrument_conflict(client):
    client.post("/instruments", json=_instrument())
    r = client.post("/instruments", json=_instrument())
    assert r.status_code == 409


# ---------------------------------------------------------------------------
# GET /instruments/{name}
# ---------------------------------------------------------------------------

def test_get_instrument(client):
    client.post("/instruments", json=_instrument(description="Test unit"))
    r = client.get("/instruments/IFCB107")
    assert r.status_code == 200
    assert r.json()["description"] == "Test unit"


def test_get_instrument_not_found(client):
    r = client.get("/instruments/MISSING")
    assert r.status_code == 404
