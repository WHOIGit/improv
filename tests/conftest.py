"""Shared test fixtures."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from amplify_db_utils import DuckDBParquetConfig, DuckDBParquetStore
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from improv.ids import ImageIdParser, ImageIdParts
from improv.oltp.models import Base
from improv.plugins.geolocation import GeoLocationPlugin
from improv.plugins.sample_context import SampleContextPlugin
from improv.service import ImageService
from improv.store.tables import register_service_tables


# ---------------------------------------------------------------------------
# Synthetic parsers for tests — no real instrument format assumed
# ---------------------------------------------------------------------------

class AlphaParser:
    """Matches IDs like 'ALPHA_20240101T120000_001'."""

    def parse(self, image_id: str) -> ImageIdParts | None:
        parts = image_id.split("_")
        if len(parts) != 3 or parts[0] != "ALPHA":
            return None
        try:
            ts = datetime.strptime(parts[1], "%Y%m%dT%H%M%S").replace(
                tzinfo=timezone.utc
            )
            return ImageIdParts(instrument="ALPHA", timestamp=ts)
        except ValueError:
            return None


class BetaParser:
    """Matches IDs like 'BETA-20240101T120000-001'."""

    def parse(self, image_id: str) -> ImageIdParts | None:
        parts = image_id.split("-")
        if len(parts) != 3 or parts[0] != "BETA":
            return None
        try:
            ts = datetime.strptime(parts[1], "%Y%m%dT%H%M%S").replace(
                tzinfo=timezone.utc
            )
            return ImageIdParts(instrument="BETA", timestamp=ts)
        except ValueError:
            return None


@pytest.fixture
def alpha_parser() -> AlphaParser:
    return AlphaParser()


@pytest.fixture
def beta_parser() -> BetaParser:
    return BetaParser()


@pytest.fixture
def parsers(alpha_parser, beta_parser) -> list:
    return [alpha_parser, beta_parser]


# ---------------------------------------------------------------------------
# Columnar store
# ---------------------------------------------------------------------------

@pytest.fixture
def store(tmp_path):
    config = DuckDBParquetConfig(root=str(tmp_path / "store"))
    return DuckDBParquetStore(config)


@pytest.fixture
def store_with_tables(store, parsers):
    plugins = [GeoLocationPlugin(), SampleContextPlugin()]
    register_service_tables(store, plugins)
    return store


# ---------------------------------------------------------------------------
# OLTP session (SQLite in-memory)
# ---------------------------------------------------------------------------

@pytest.fixture
def session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    sess = Session()
    yield sess
    sess.close()
    engine.dispose()


# ---------------------------------------------------------------------------
# Full service
# ---------------------------------------------------------------------------

@pytest.fixture
def service(store_with_tables, session, parsers):
    plugins = [GeoLocationPlugin(), SampleContextPlugin()]
    return ImageService(
        store=store_with_tables,
        session=session,
        parsers=parsers,
        plugins=plugins,
    )


# ---------------------------------------------------------------------------
# Common timestamps
# ---------------------------------------------------------------------------

@pytest.fixture
def ts_jan():
    return datetime(2024, 1, 15, 12, 0, 0, tzinfo=timezone.utc)


@pytest.fixture
def ts_feb():
    return datetime(2024, 2, 15, 12, 0, 0, tzinfo=timezone.utc)
