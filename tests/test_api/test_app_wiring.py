"""Production startup path — create_app, lifespan, and per-request sessions.

The `client` fixture builds an app without a lifespan, so these tests are the
only coverage of what create_app actually assembles at boot.
"""

from __future__ import annotations

import threading

import pytest
from amplify_db_utils import DuckDBParquetConfig
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from improv.api.app import create_app
from improv.api.deps import get_service
from improv.config import ImprovConfig
from improv.oltp.models import Base
from improv.plugins.geolocation import GeoLocationPlugin
from improv.plugins.sample_context import SampleContextPlugin


@pytest.fixture
def config(tmp_path):
    return ImprovConfig(
        db_config=DuckDBParquetConfig(root=str(tmp_path / "store")),
        database_url=f"sqlite:///{tmp_path / 'oltp.db'}",
        parsers=[],
        plugins=[GeoLocationPlugin(), SampleContextPlugin()],
        api_token="boot-token",
    )


# --- lifespan --------------------------------------------------------------

def test_lifespan_registers_tables_and_state(config):
    """Booting must register every plugin index table, not just images/provenance."""
    app = create_app(config)
    with TestClient(app):
        assert app.state.session_factory is not None
        assert app.state.config is config

        store = app.state.store
        # get_schema raises KeyError for a table that was never registered.
        expected = ["images", "provenance"] + [
            p.index_table for p in config.plugins if p.index_table
        ]
        for table in expected:
            assert store.get_schema(table) is not None


def test_healthz_is_open_and_shallow(config):
    app = create_app(config)
    with TestClient(app) as client:
        client.headers.pop("Authorization", None)
        resp = client.get("/healthz")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


# --- per-request session ---------------------------------------------------
#
# A Session is not thread-safe and every route is a sync def, so FastAPI runs
# them in a threadpool. These tests pin that each request gets its own Session
# and that it is closed afterwards.


def _session_probe_app(engine):
    """Minimal app exposing the Session identity that get_service handed out."""
    app = FastAPI()
    app.state.store = None
    app.state.session_factory = sessionmaker(bind=engine)
    app.state.config = ImprovConfig(
        db_config=DuckDBParquetConfig(root="/unused"),
        database_url="sqlite:///:memory:",
    )

    seen: list[int] = []
    lock = threading.Lock()

    @app.get("/probe")
    def probe(service=Depends(get_service)) -> dict:
        with lock:
            seen.append(id(service._session))
        return {"session_id": id(service._session)}

    return app, seen


@pytest.fixture
def probe(tmp_path):
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    app, seen = _session_probe_app(engine)
    with TestClient(app) as client:
        yield client, seen
    engine.dispose()


def test_each_request_gets_a_distinct_session(probe):
    client, _ = probe
    first = client.get("/probe").json()["session_id"]
    second = client.get("/probe").json()["session_id"]
    assert first != second


def test_concurrent_requests_get_distinct_sessions(probe):
    """The threadpool case: overlapping requests must not share a Session."""
    client, seen = probe
    barrier = threading.Barrier(4, timeout=10)
    results: list[int] = []
    results_lock = threading.Lock()

    def hit():
        barrier.wait()  # ensure the requests genuinely overlap
        sid = client.get("/probe").json()["session_id"]
        with results_lock:
            results.append(sid)

    threads = [threading.Thread(target=hit) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=20)

    assert len(results) == 4
    assert len(set(results)) == 4, "sessions were shared across concurrent requests"


def test_session_is_closed_after_request(probe):
    """The dependency's finally block must release the Session."""
    client, _ = probe
    captured: list = []

    app = client.app
    original = app.state.session_factory

    def tracking_factory():
        session = original()
        captured.append(session)
        return session

    app.state.session_factory = tracking_factory
    client.get("/probe")

    assert len(captured) == 1
    # A closed Session has no active connection bound to it.
    assert not captured[0].is_active or captured[0].get_transaction() is None
