"""FastAPI application factory."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

from fastapi import FastAPI

if TYPE_CHECKING:
    from improv.config import ImprovConfig


def create_app(config: "ImprovConfig") -> FastAPI:
    """Create and configure the FastAPI application.

    Registers service tables at startup via lifespan, injects ImageService
    via app.state for use in route dependencies.
    """
    from amplify_db_utils import DuckDBParquetStore, DuckDBParquetConfig
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from improv.api.auth import StaticTokenVerifier
    from improv.api.routers import blobs, classification, datasets, images, ingest_tasks, instruments, provenance, samples
    from improv.oltp.models import Base
    from improv.service import ImageService
    from improv.store.tables import register_service_tables

    if not config.api_token:
        raise RuntimeError(
            "IMPROV_API_TOKEN is required to serve the REST surface "
            "(set config.api_token). Refusing to start a protected API with no token."
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
        engine = create_engine(config.database_url or "sqlite:///:memory:")
        Base.metadata.create_all(engine)
        Session = sessionmaker(bind=engine)
        session = Session()

        register_service_tables(store, config.plugins)

        app.state.service = ImageService(
            store=store,
            session=session,
            parsers=config.parsers,
            plugins=config.plugins,
            storage=config.storage,
        )
        yield
        session.close()

    app = FastAPI(
        title="improv",
        description="Image provenance substrate for scientific imaging instruments.",
        lifespan=lifespan,
    )

    # Single construction site for auth — swap StaticTokenVerifier for a
    # DbTokenVerifier here when tokens move to per-client storage.
    app.state.verifier = StaticTokenVerifier(config.api_token)

    app.include_router(images.router)
    app.include_router(provenance.router)
    app.include_router(instruments.router)
    app.include_router(samples.router)
    app.include_router(blobs.router)
    app.include_router(datasets.router)
    app.include_router(ingest_tasks.router)
    app.include_router(classification.router)

    return app
