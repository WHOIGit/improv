"""Production startup path — create_app, lifespan, and per-request sessions.

The `client` fixture builds an app without a lifespan, so these tests are the
only coverage of what create_app actually assembles at boot.
"""

from __future__ import annotations

import threading
from pathlib import Path

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
from improv.plugins.blob import BlobPlugin
from improv.plugins.geolocation import GeoLocationPlugin
from improv.plugins.ifcb.features import IFCBFeaturesPlugin
from improv.plugins.sample_context import SampleContextPlugin
from improv.store.build import build_store
from improv.store.tables import create_service_tables


@pytest.fixture
def unprovisioned(tmp_path):
    """Config whose columnar store exists but has never been synced."""
    return ImprovConfig(
        db_config=DuckDBParquetConfig(root=str(tmp_path / "store")),
        database_url=f"sqlite:///{tmp_path / 'oltp.db'}",
        parsers=[],
        plugins=[GeoLocationPlugin(), SampleContextPlugin()],
        api_token="boot-token",
    )


@pytest.fixture
def config(unprovisioned):
    """The normal case: `improv schema sync` has already run.

    Startup only declares tables, so every boot test needs them to exist
    first — exactly as the compose `schema-sync` one-shot guarantees in
    production.
    """
    create_service_tables(build_store(unprovisioned), unprovisioned.plugins)
    return unprovisioned


def _registry_path(config) -> Path:
    return Path(config.db_config.root) / "_registry" / "tables.json"


# --- lifespan --------------------------------------------------------------

def test_lifespan_declares_tables_and_state(config):
    """Booting must declare every plugin index table, not just images/provenance."""
    app = create_app(config)
    with TestClient(app):
        assert app.state.session_factory is not None
        assert app.state.config is config

        store = app.state.store
        # get_schema raises KeyError for a table that was never declared.
        expected = ["images", "provenance"] + [
            p.index_table for p in config.plugins if p.index_table
        ]
        for table in expected:
            assert store.get_schema(table) is not None


def test_lifespan_creates_nothing(config):
    """Booting must not write the schema registry — that is schema sync's job.

    With WEB_CONCURRENCY > 1 this path runs once per uvicorn worker,
    concurrently, and no columnar backend offers an atomic create-if-absent
    (VastDB's fail_if_exists is a client-side check before an unconditional
    create RPC). Several workers would each see an absent table and each try
    to create it.

    The DuckDB backend stands in for both here: its registry sidecar is the
    observable artifact of creation, written under the same unlocked
    read-modify-write. Sync has already written it, so the test is that boot
    leaves the bytes untouched. If this fails, startup has regressed to
    calling create_table and the race is back.
    """
    before = _registry_path(config).read_bytes()

    app = create_app(config)
    with TestClient(app):
        pass

    assert _registry_path(config).read_bytes() == before, (
        "service startup rewrote the columnar schema registry — startup must "
        "declare tables (register_table), never create them"
    )


def test_lifespan_refuses_to_start_when_tables_are_missing(unprovisioned):
    """Skipping `improv schema sync` must fail at boot, not on the first write.

    Declaring believes whatever it is told, so without the verification step
    the service would serve until something tried to write and then fail with
    a backend-level "table not found" pointing nowhere near the cause.
    """
    app = create_app(unprovisioned)

    with pytest.raises(RuntimeError, match="improv schema sync"):
        with TestClient(app):
            pass


def test_lifespan_refuses_to_start_when_a_plugin_index_is_missing(config):
    """The realistic case: a plugin was added to IMPROV_PLUGINS without re-syncing."""
    config.plugins = list(config.plugins) + [BlobPlugin(), IFCBFeaturesPlugin()]

    app = create_app(config)

    with pytest.raises(RuntimeError, match="ifcb_features_index"):
        with TestClient(app):
            pass


def test_engine_pre_pings_pooled_connections(config):
    """Stale pooled connections must be recycled before a request sees them."""
    app = create_app(config)
    with TestClient(app):
        engine = app.state.session_factory.kw["bind"]
        assert engine.pool._pre_ping is True


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
