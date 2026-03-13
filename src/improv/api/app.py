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
    from amplify_db_utils import DuckDBParquetStore
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from improv.api.routers import blobs, datasets, images, instruments, provenance, samples
    from improv.oltp.models import Base
    from improv.service import ImageService
    from improv.store.tables import register_service_tables

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        store = DuckDBParquetStore(config.db_config)
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

    app.include_router(images.router)
    app.include_router(provenance.router)
    app.include_router(instruments.router)
    app.include_router(samples.router)
    app.include_router(blobs.router)
    app.include_router(datasets.router)

    return app
