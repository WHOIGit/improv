"""Token-auth enforcement on the REST surface.

The `client` fixture authenticates by default (see conftest.TEST_TOKEN), so
these tests strip or override the Authorization header to exercise the
unauthenticated / wrong-token paths.
"""

from __future__ import annotations

import pytest
from amplify_db_utils import DuckDBParquetConfig

from improv.api.app import create_app
from improv.api.auth import StaticTokenVerifier
from improv.client import ImprovClient
from improv.config import ImprovConfig
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


# --- malformed credentials -------------------------------------------------

def test_explicit_valid_token_accepted(client):
    _unauth(client)
    resp = client.post(
        "/ingest-tasks",
        json={"task_id": "t1"},
        headers={"Authorization": f"Bearer {TEST_TOKEN}"},
    )
    assert resp.status_code == 201


@pytest.mark.parametrize(
    "header",
    [
        "Basic dXNlcjpwYXNz",  # wrong scheme
        "Bearer",  # scheme with no credentials
        f"{TEST_TOKEN}",  # bare token, no scheme
    ],
)
def test_malformed_authorization_header_rejected(client, header):
    _unauth(client)
    resp = client.post(
        "/ingest-tasks", json={"task_id": "t1"}, headers={"Authorization": header}
    )
    assert resp.status_code == 401


def test_non_ascii_token_is_rejected_not_500(client):
    """Regression: header values arrive latin-1 decoded, and secrets.compare_digest
    raises TypeError on non-ASCII str, which surfaced as a 500 from the auth path."""
    _unauth(client)
    resp = client.post(
        "/ingest-tasks",
        json={"task_id": "t1"},
        headers=[(b"authorization", b"Bearer t\xf6ken")],
    )
    assert resp.status_code == 401


def test_verifier_rejects_non_ascii_token():
    verifier = StaticTokenVerifier(TEST_TOKEN)
    assert verifier.verify("tökén") is None


# --- create_app wiring -----------------------------------------------------

def test_create_app_requires_token(tmp_path):
    config = ImprovConfig(
        db_config=DuckDBParquetConfig(root=str(tmp_path / "store")),
        database_url="sqlite:///:memory:",
    )
    with pytest.raises(RuntimeError, match="IMPROV_API_TOKEN"):
        create_app(config)


def test_create_app_requires_database_url(tmp_path):
    """No OLTP URL must fail loudly, not fall back to in-memory SQLite."""
    config = ImprovConfig(
        db_config=DuckDBParquetConfig(root=str(tmp_path / "store")),
        api_token="wired-token",
    )
    with pytest.raises(RuntimeError, match="IMPROV_DATABASE_URL"):
        create_app(config)


def test_create_app_installs_verifier(tmp_path):
    config = ImprovConfig(
        db_config=DuckDBParquetConfig(root=str(tmp_path / "store")),
        database_url="sqlite:///:memory:",
        api_token="wired-token",
    )
    app = create_app(config)
    verifier = app.state.verifier
    assert verifier.verify("wired-token") is not None
    assert verifier.verify("nope") is None


# --- client token plumbing -------------------------------------------------

def test_client_reads_token_from_env(monkeypatch):
    monkeypatch.setenv("IMPROV_API_TOKEN", "env-token")
    c = ImprovClient(base_url="http://testserver")
    assert c._client.headers["Authorization"] == "Bearer env-token"


def test_client_explicit_token_overrides_env(monkeypatch):
    monkeypatch.setenv("IMPROV_API_TOKEN", "env-token")
    c = ImprovClient(base_url="http://testserver", token="explicit")
    assert c._client.headers["Authorization"] == "Bearer explicit"


def test_client_without_token_sends_no_header(monkeypatch):
    monkeypatch.delenv("IMPROV_API_TOKEN", raising=False)
    c = ImprovClient(base_url="http://testserver")
    assert "Authorization" not in c._client.headers
