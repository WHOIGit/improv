"""Columnar store operations for service-owned index tables.

Cross-index joins: always use select="right".
When joining geolocation_index or sample_index against images, pass
select="right" to store.join(). Both tables share partition key columns;
select="both" returns duplicate columns. select="right" returns only the
payload (images) table's columns.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING

from improv.plugins.geolocation import GeoLocationIndexRecord
from improv.plugins.sample_context import SampleIndexRecord

if TYPE_CHECKING:
    from amplify_db_utils import ColumnarStore


def _as_utc(ts: datetime) -> datetime:
    if ts.tzinfo is None:
        return ts.replace(tzinfo=timezone.utc)
    return ts


def write_geolocation(
    store: "ColumnarStore",
    records: list[GeoLocationIndexRecord],
) -> None:
    """Write geolocation index records."""
    store.write("geolocation_index", [r.model_dump() for r in records])


def query_spatial(
    store: "ColumnarStore",
    lat_min: float,
    lat_max: float,
    lon_min: float,
    lon_max: float,
    time_start: datetime | None = None,
    time_end: datetime | None = None,
) -> list[str]:
    """Return image_ids within a lat/lon bounding box, optionally scoped by time.

    Time filtering uses the year/month partition keys for efficient pruning
    (month-level precision). Callers may apply exact timestamp filtering
    against the images table afterward.
    """
    filters: dict = {
        "lat": {"gte": lat_min, "lte": lat_max},
        "lon": {"gte": lon_min, "lte": lon_max},
    }
    # Approximate time scoping via partition keys when both bounds are in the same year
    if time_start is not None and time_end is not None:
        time_start = _as_utc(time_start)
        time_end = _as_utc(time_end)
        if time_start.year == time_end.year:
            filters["year"] = time_start.year
            if time_start.month == time_end.month:
                filters["month"] = time_start.month

    return [
        row["image_id"]
        for row in store.read("geolocation_index", filters=filters)
    ]


def write_sample_index(
    store: "ColumnarStore",
    records: list[SampleIndexRecord],
) -> None:
    """Write sample index records."""
    store.write("sample_index", [r.model_dump() for r in records])


def get_images_by_sample_id(
    store: "ColumnarStore",
    sample_id: str,
    source: str | None = None,
) -> list[str]:
    """Return image_ids associated with a sample ID.

    An image may have multiple sample_index rows (one per naming scheme / source).
    Pass source to restrict to a specific naming authority.
    """
    filters: dict = {"sample_id": sample_id}
    if source is not None:
        filters["source"] = source
    return [row["image_id"] for row in store.read("sample_index", filters=filters)]
