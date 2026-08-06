"""FastAPI application factory."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

from fastapi import FastAPI

if TYPE_CHECKING:
    from improv.config import ImprovConfig


def create_app(config: "ImprovConfig") -> FastAPI:
    """Create and configure the FastAPI application.

    Registers service tables at startup via lifespan and publishes the
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
    from amplify_db_utils import DuckDBParquetStore, DuckDBParquetConfig
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from improv.api.auth import StaticTokenVerifier
    from improv.api.routers import blobs, classification, datasets, images, ingest_tasks, instruments, provenance, samples
    from improv.store.tables import register_service_tables

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
        # DuckDB checked first so non-VAST deployments never import vastdb.
        if isinstance(config.db_config, DuckDBParquetConfig):
            store = DuckDBParquetStore(config.db_config)
        else:
            try:
                from amplify_db_utils.vastdb_store import VastDBConfig, VastDBStore
            except ImportError:
                # vastdb not installed, so db_config cannot be a VastDBConfig —
                # report the config error rather than the missing driver.
                raise RuntimeError(
                    f"Unsupported db_config type: {type(config.db_config).__name__}"
                )

            if isinstance(config.db_config, VastDBConfig):
                store = VastDBStore(config.db_config)
            else:
                raise RuntimeError(
                    f"Unsupported db_config type: {type(config.db_config).__name__}"
                )

        # Schema is owned by Alembic (`improv db upgrade`), not by startup:
        # create_all here would leave alembic_version unstamped and let the
        # real schema drift from the migration history.
        engine = create_engine(config.database_url)

        register_service_tables(store, config.plugins)

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
