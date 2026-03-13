"""Columnar store operations for the images table."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING, Iterator

import pyarrow as pa

from improv.ids import ImageIdParser, make_partition_keys
from improv.models.image import ImageRecord

if TYPE_CHECKING:
    from amplify_db_utils import ColumnarStore


def _as_utc(ts: datetime) -> datetime:
    if ts.tzinfo is None:
        return ts.replace(tzinfo=timezone.utc)
    return ts


def _enrich(record: dict, parsers: list[ImageIdParser]) -> dict:
    """Populate instrument, year, month partition keys in a record dict.

    instrument comes from the parser (or existing value as hint fallback).
    year/month always come from the record's own timestamp — the canonical source.
    """
    r = dict(record)
    ts = r["timestamp"]
    if isinstance(ts, str):
        ts = datetime.fromisoformat(ts)
    ts = _as_utc(ts)
    r["timestamp"] = ts

    keys = make_partition_keys(
        r["image_id"], parsers, instrument_hint=r.get("instrument")
    )
    r["instrument"] = keys["instrument"]
    r["year"] = ts.year
    r["month"] = ts.month
    return r


def write_images(
    store: "ColumnarStore",
    records: list[ImageRecord],
    parsers: list[ImageIdParser],
) -> None:
    """Write image records to the columnar store.

    Enriches each record with partition key fields before writing.
    """
    dicts = [_enrich(r.model_dump(), parsers) for r in records]
    store.write("images", dicts)


def get_image(
    store: "ColumnarStore",
    image_id: str,
    parsers: list[ImageIdParser],
    instrument_hint: str | None = None,
) -> ImageRecord | None:
    """Retrieve a single image record by ID.

    Uses parsers to derive partition keys for efficient lookup. Falls back to
    instrument_hint (scans all of that instrument's partitions).
    """
    keys = make_partition_keys(image_id, parsers, instrument_hint)
    filters: dict = {"image_id": image_id, **keys}
    for row in store.read("images", filters=filters):
        return ImageRecord(**row)
    return None


def get_images(
    store: "ColumnarStore",
    instrument: str,
    time_start: datetime,
    time_end: datetime,
) -> Iterator[ImageRecord]:
    """Iterate image records for an instrument within a time window."""
    filters = {
        "instrument": instrument,
        "timestamp": {"gte": _as_utc(time_start), "lte": _as_utc(time_end)},
    }
    for row in store.read("images", filters=filters):
        yield ImageRecord(**row)


def bulk_get_images(
    store: "ColumnarStore",
    instrument: str,
    time_start: datetime,
    time_end: datetime,
) -> pa.Table:
    """Bulk-read image records as a PyArrow Table (zero-copy)."""
    filters = {
        "instrument": instrument,
        "timestamp": {"gte": _as_utc(time_start), "lte": _as_utc(time_end)},
    }
    return store.bulk_read("images", filters=filters)
