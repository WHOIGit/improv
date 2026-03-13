"""Geolocation provenance plugin.

Handles kind="geolocation". Maintains a geolocation_index table for
spatial queries. Geolocation is computed from ancillary data (nav track
interpolation, sample metadata) and is versioned and re-runnable.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from pydantic import BaseModel

if TYPE_CHECKING:
    from amplify_db_utils import ColumnarStore
    from improv.models.provenance import ProvenanceEnvelope


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
