"""Thread-safety of the columnar store under the service's access pattern.

Every API route handler is a sync ``def``, so FastAPI runs them in a threadpool
and the process-wide store is read from many threads at once. This module pins
what that actually does.

The DuckDB+Parquet backend does not survive it: ``DuckDBParquetStore`` issues
every query on one shared DuckDB connection (``duckdb_parquet.py`` ``read``
does ``cursor = self._conn.execute(...)``, and ``DuckDBPyConnection.execute``
returns the connection itself, holding a single result set). Because ``read()``
is a generator, fetching interleaves with the caller's consumption, so a second
query replaces the first's pending result and the first returns no rows.

That is silent wrong data, not an error. The upstream fix is to take an
independent ``self._conn.cursor()`` per call; verified locally to take the
failure rate from ~49/100 to 0/100.

The xfail below is non-strict so it flips to XPASS — not a failure — once
amplify-db-utils is fixed. When that happens, drop the marker.
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


@pytest.mark.xfail(
    reason="DuckDBParquetStore shares one DuckDB connection across threads; "
    "concurrent reads clobber each other's result set and return no rows. "
    "Fix upstream in amplify-db-utils with a per-call self._conn.cursor().",
    strict=False,
)
def test_concurrent_reads_are_reliable(populated_store):
    """Concurrent reads of a present record must all find it."""
    with cf.ThreadPoolExecutor(max_workers=THREADS) as ex:
        found = list(ex.map(lambda _: _read_once(populated_store), range(READS)))

    misses = found.count(False)
    assert misses == 0, (
        f"{misses}/{READS} concurrent reads returned no rows for a record that "
        "is present — the store returned wrong data rather than raising"
    )
