"""Token-auth enforcement on the REST surface.

The `client` fixture authenticates by default (see conftest.TEST_TOKEN), so
these tests strip or override the Authorization header to exercise the
unauthenticated / wrong-token paths.
"""

from __future__ import annotations

from tests.test_api.conftest import TEST_TOKEN

WRONG = {"Authorization": "Bearer wrong-token"}


def _unauth(client):
    """Drop the fixture's default bearer header for this client."""
    client.headers.pop("Authorization", None)
    return client


# --- write scope -----------------------------------------------------------

def test_write_endpoint_requires_token(client):
    _unauth(client)
    resp = client.post("/ingest-tasks", json={"task_id": "t1"})
    assert resp.status_code == 401


def test_write_endpoint_rejects_wrong_token(client):
    resp = client.post("/ingest-tasks", json={"task_id": "t1"}, headers=WRONG)
    assert resp.status_code == 401


def test_write_endpoint_accepts_valid_token(client):
    # Fixture already sends the valid token; assert we're past auth (created).
    resp = client.post("/ingest-tasks", json={"task_id": "t1"})
    assert resp.status_code == 201


# --- read scope ------------------------------------------------------------

def test_ingest_task_read_requires_token(client):
    _unauth(client)
    resp = client.get("/ingest-tasks/whatever")
    assert resp.status_code == 401


def test_decode_requires_token(client):
    _unauth(client)
    resp = client.post(
        "/classifiers/c1/decode",
        json={"model_version": "v1", "scores": [0.1, 0.9], "winner_index": 1},
    )
    assert resp.status_code == 401


# --- open endpoints stay open ----------------------------------------------

def test_open_read_needs_no_token(client):
    _unauth(client)
    # Missing query params → 400 (not 401): the route ran without auth.
    resp = client.get("/images/search")
    assert resp.status_code == 400


def test_taxonomy_read_needs_no_token(client):
    _unauth(client)
    resp = client.get("/classifiers/c1/taxonomies/v1")
    assert resp.status_code == 404  # not found, not unauthorized
