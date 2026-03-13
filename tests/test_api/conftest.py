"""API test fixtures.

Builds a bare FastAPI app with routers but no lifespan, injecting the service
directly via app.state. This avoids SQLite threading issues and keeps tests
independent of production startup logic.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from amplify_db_utils import DuckDBParquetConfig, DuckDBParquetStore
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from improv.api.routers import blobs, datasets, images, provenance, samples
from improv.oltp.models import Base
from improv.plugins.geolocation import GeoLocationPlugin
from improv.plugins.sample_context import SampleContextPlugin
from improv.service import ImageService
from improv.store.tables import register_service_tables

from tests.conftest import AlphaParser


@pytest.fixture
def client(tmp_path):
    db_config = DuckDBParquetConfig(root=str(tmp_path / "store"))
    store = DuckDBParquetStore(db_config)

    # StaticPool + check_same_thread=False: single shared connection so all
    # create_all / session calls see the same in-memory SQLite database.
    from sqlalchemy.pool import StaticPool
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()

    plugins = [GeoLocationPlugin(), SampleContextPlugin()]
    parsers = [AlphaParser()]
    register_service_tables(store, plugins)

    service = ImageService(
        store=store,
        session=session,
        parsers=parsers,
        plugins=plugins,
    )

    app = FastAPI()
    app.state.service = service
    app.include_router(images.router)
    app.include_router(provenance.router)
    app.include_router(samples.router)
    app.include_router(blobs.router)
    app.include_router(datasets.router)

    with TestClient(app) as c:
        yield c
