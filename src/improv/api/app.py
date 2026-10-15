"""FastAPI application factory."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

from fastapi import FastAPI

if TYPE_CHECKING:
    from improv.config import ImprovConfig


def create_app(config: "ImprovConfig") -> FastAPI:
    """Create and configure the FastAPI application.

    Declares the service tables at startup via lifespan — declares, not
    creates: run ``improv schema sync`` before serving. Publishes the
    long-lived components on ``app.state`` for route dependencies to consume:

      ``app.state.store``            columnar store, shared process-wide
      ``app.state.session_factory``  sessionmaker; deps build one Session per request
      ``app.state.config``           parsers, plugins, object store
      ``app.state.verifier``         token verifier

    The columnar store is shared deliberately — VastDBStore opens a fresh
    transaction per call, and DuckDBParquetStore holds no cross-call state. The
    SQLAlchemy Session is *not* shared: it is not thread-safe, and every route
    is a sync ``def`` that FastAPI runs in a threadpool.
    """
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from improv.api.auth import StaticTokenVerifier
    from improv.api.routers import blobs, classification, datasets, images, ingest_tasks, instruments, provenance, samples
    from improv.store.build import build_store
    from improv.store.tables import declare_service_tables, verify_service_tables

    if not config.api_token:
        raise RuntimeError(
            "IMPROV_API_TOKEN is required to serve the REST surface "
            "(set config.api_token). Refusing to start a protected API with no token."
        )

    if not config.database_url:
        raise RuntimeError(
            "IMPROV_DATABASE_URL is required to serve the REST surface "
            "(set config.database_url). Refusing to start with no OLTP database: "
            "an in-memory fallback would accept writes and persist nothing."
        )

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        store = build_store(config)

        # Schema is owned by Alembic (`improv db upgrade`), not by startup:
        # create_all here would leave alembic_version unstamped and let the
        # real schema drift from the migration history.
        #
        # pool_pre_ping: pooled connections go stale when Postgres restarts or a
        # firewall/idle timeout drops them. Without it the first request to grab a
        # stale connection fails and only then is it recycled. The pre-checkout
        # liveness probe costs ~0.1ms per checkout — cheap next to a 500.
        engine = create_engine(config.database_url, pool_pre_ping=True)

        # Declare, do not create. The columnar schema is owned by
        # `improv schema sync`, for the same reason the OLTP schema is owned by
        # Alembic — and additionally because creating it here races. With
        # WEB_CONCURRENCY > 1 this runs once per worker, concurrently, and no
        # backend offers an atomic create-if-absent (see improv.store.tables).
        # register_table only populates in-process metadata, so it is safe to
        # run in every worker.
        declare_service_tables(store, config.plugins)

        # Then check the tables are actually there. Declaring is a local
        # operation and believes whatever it is told, so without this a
        # deployment that skipped `improv schema sync` would serve until the
        # first write and then fail with a backend-level "table not found".
        # This is a read, so it cannot race the way creation did.
        verify_service_tables(store, config.plugins)

        app.state.store = store
        app.state.session_factory = sessionmaker(bind=engine)
        app.state.config = config
        try:
            yield
        finally:
            engine.dispose()

    app = FastAPI(
        title="improv",
        description="Image provenance substrate for scientific imaging instruments.",
        lifespan=lifespan,
    )

    # Single construction site for auth — swap StaticTokenVerifier for a
    # DbTokenVerifier here when tokens move to per-client storage.
    app.state.verifier = StaticTokenVerifier(config.api_token)

    @app.get("/healthz", tags=["ops"])
    def healthz() -> dict:
        """Liveness probe.

        Deliberately shallow — no Postgres or VAST round-trip. A dependency
        blip should surface on the affected endpoints, not cause an
        orchestrator to kill an otherwise-serving process.
        """
        return {"status": "ok"}

    app.include_router(images.router)
    app.include_router(provenance.router)
    app.include_router(instruments.router)
    app.include_router(samples.router)
    app.include_router(blobs.router)
    app.include_router(datasets.router)
    app.include_router(ingest_tasks.router)
    app.include_router(classification.router)

    return app
