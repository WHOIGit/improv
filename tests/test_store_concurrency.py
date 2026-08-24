"""Thread-safety of the columnar store under the service's access pattern.

Every API route handler is a sync ``def``, so FastAPI runs them in a threadpool
and the process-wide store is read from many threads at once. This module pins
what that actually does.

This used to fail. ``DuckDBParquetStore`` issued every query on one shared
DuckDB connection, and a connection holds exactly one pending result, so a
second query silently discarded the first's remaining rows — which corrupts a
lazy generator like ``read()`` whenever two are interleaved or run from
different threads. It failed as wrong data, never as an error: ~49 of 100
concurrent reads returned nothing for a record that was present.

Fixed upstream in amplify-db-utils v0.1.1, which takes a fresh
``self._conn.cursor()`` per query (and re-applies LOCAL-scope settings to it,
which a bare ``cursor()`` would drop). Keep this test: the failure mode is
invisible without it, and every API route handler is a sync ``def``, so the
process-wide store really is read from many threads at once in production.
"""

from __future__ import annotations

import concurrent.futures as cf
from datetime import datetime, timezone

import pytest
from amplify_db_utils import DuckDBParquetConfig, DuckDBParquetStore

from improv.models.image import ImageRecord
from improv.store.tables import register_service_tables

TS = datetime(2024, 1, 15, 12, 0, tzinfo=timezone.utc)
IMAGE_ID = "D20240115T120000_IFCB107_00001"
FILTERS = {"image_id": IMAGE_ID, "instrument": "IFCB107", "year": 2024, "month": 1}

THREADS = 16
READS = 64


@pytest.fixture
def populated_store(tmp_path):
    store = DuckDBParquetStore(DuckDBParquetConfig(root=str(tmp_path / "store")))
    register_service_tables(store, [])
    store.write(
        "images",
        [
            ImageRecord(
                image_id=IMAGE_ID,
                timestamp=TS,
                instrument="IFCB107",
                year=2024,
                month=1,
            ).model_dump()
        ],
    )
    return store


def _read_once(store) -> bool:
    """True if the known-present record was returned."""
    return bool(list(store.read("images", filters=FILTERS)))


def test_single_threaded_read_is_reliable(populated_store):
    """Baseline: the record is readable when nothing is concurrent."""
    assert all(_read_once(populated_store) for _ in range(READS))


def test_concurrent_reads_are_reliable(populated_store):
    """Concurrent reads of a present record must all find it."""
    with cf.ThreadPoolExecutor(max_workers=THREADS) as ex:
        found = list(ex.map(lambda _: _read_once(populated_store), range(READS)))

    misses = found.count(False)
    assert misses == 0, (
        f"{misses}/{READS} concurrent reads returned no rows for a record that "
        "is present — the store returned wrong data rather than raising"
    )
