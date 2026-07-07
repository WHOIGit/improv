"""Geolocation provenance plugin.

Handles kind="geolocation". Maintains a geolocation_index table for
spatial queries. Geolocation is computed from ancillary data (nav track
interpolation, sample metadata) and is versioned and re-runnable.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING

from pydantic import BaseModel

if TYPE_CHECKING:
    from amplify_db_utils import ColumnarStore
    from improv.models.provenance import ProvenanceEnvelope


def _as_utc(ts: datetime) -> datetime:
    if ts.tzinfo is None:
        return ts.replace(tzinfo=timezone.utc)
    return ts


class GeoLocationRecord(BaseModel):
    """Payload schema for geolocation provenance records (goes in data field)."""
    lat: float
    lon: float
    depth: float | None = None
    source: str
    version: str
    computed_at: datetime


class GeoLocationIndexRecord(BaseModel):
    """Index record for fast spatial queries."""
    image_id: str
    lat: float
    lon: float
    depth: float | None = None
    source: str
    version: str
    computed_at: datetime
    # Partition keys
    instrument: str | None = None
    year: int | None = None
    month: int | None = None


class GeoLocationPlugin:
    kind = "geolocation"
    index_table = "geolocation_index"
    index_schema = GeoLocationIndexRecord
    partition_by = ["instrument", "year", "month"]

    def create_index(self, store: "ColumnarStore") -> None:
        store.create_table(
            self.index_table,
            self.index_schema,
            partition_by=self.partition_by,
        )

    def extract_index_record(self, envelope: "ProvenanceEnvelope") -> dict | None:
        data = envelope.data
        return {
            "image_id": envelope.image_id,
            "lat": data["lat"],
            "lon": data["lon"],
            "depth": data.get("depth"),
            "source": data["source"],
            "version": data["version"],
            "computed_at": data["computed_at"],
            "instrument": envelope.instrument,
            "year": envelope.year,
            "month": envelope.month,
        }

    # --- SpatialQueryPlugin capability -------------------------------------

    def write_index(
        self,
        store: "ColumnarStore",
        records: list[GeoLocationIndexRecord],
    ) -> None:
        """Batch-write geolocation index records."""
        store.write(self.index_table, [r.model_dump() for r in records])

    def query_spatial(
        self,
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
        # Approximate time scoping via partition keys when both bounds share a year
        if time_start is not None and time_end is not None:
            time_start = _as_utc(time_start)
            time_end = _as_utc(time_end)
            if time_start.year == time_end.year:
                filters["year"] = time_start.year
                if time_start.month == time_end.month:
                    filters["month"] = time_start.month

        return [
            row["image_id"]
            for row in store.read(self.index_table, filters=filters)
        ]
