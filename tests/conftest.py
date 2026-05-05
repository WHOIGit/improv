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

import os
import uuid
import pytest

from amplify_db_utils import DuckDBParquetConfig, DuckDBParquetStore
from amplify_db_utils.vastdb_store import VastDBConfig, VastDBStore

_BACKENDS = ["duckdb"]
if os.environ.get("IMPROV_TEST_VASTDB") == "1":
    _BACKENDS.append("vastdb")

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

@pytest.fixture(params=_BACKENDS)
def store(request, tmp_path):
    if request.param == "duckdb":
        cfg = DuckDBParquetConfig(root=str(tmp_path / "store"))
        yield DuckDBParquetStore(cfg)
        return

    # VastDB: per-test unique schema for isolation, torn down after.
    cfg = VastDBConfig(
        endpoint=os.environ["IMPROV_TEST_VASTDB_ENDPOINT"],
        access_key=os.environ["IMPROV_TEST_VASTDB_ACCESS_KEY"],
        secret_key=os.environ["IMPROV_TEST_VASTDB_SECRET_KEY"],
        bucket=os.environ["IMPROV_TEST_VASTDB_BUCKET"],
        schema=f"improv_test_{uuid.uuid4().hex[:8]}",
        add_written_at=True,
    )
    s = VastDBStore(cfg)
    try:
        yield s
    finally:
        s.drop_schema()


@pytest.fixture
def store_with_tables(store, parsers):
    plugins = [GeoLocationPlugin(), SampleContextPlugin()]
    register_service_tables(store, plugins)
    return store


# ---------------------------------------------------------------------------
# OLTP (SQLite in-memory)
# ---------------------------------------------------------------------------

@pytest.fixture
def engine():
    eng = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(eng)
    yield eng
    eng.dispose()


@pytest.fixture
def session(engine):
    Session = sessionmaker(bind=engine)
    sess = Session()
    yield sess
    sess.close()


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
