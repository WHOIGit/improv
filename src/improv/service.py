"""ImageService — central business logic object.

Owns a ColumnarStore, a SQLAlchemy Session, registered ImageIdParsers,
registered ProvenancePlugins, and an optional ObjectStore.

Ingest flows:
  ingest_images       — write to columnar store
  ingest_provenance   — write to provenance table; dual-write index via plugin

Retrieval flows:
  get_image           — point lookup
  get_provenance      — full or kind-filtered provenance log for one image
  query_images        — time-range ± spatial filter
  get_sample          — OLTP sample record
  get_sample_images   — time-range query scoped to a sample's bounds
  get_dataset_images  — multi-span query for a named dataset
  get_blob_key        — resolve storage key for a binary product
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Iterator

from improv.store.images import (
    bulk_get_images,
    get_image,
    get_images,
    write_images,
)
from improv.store.indexes import get_images_by_sample_id, query_spatial
from improv.store.provenance import (
    get_provenance,
    get_provenance_by_kind,
    write_provenance,
)

if TYPE_CHECKING:
    import pyarrow as pa
    from amplify_db_utils import ColumnarStore
    from sqlalchemy.orm import Session
    from storage.object import ObjectStore

    from improv.ids import ImageIdParser
    from improv.models.image import ImageRecord
    from improv.models.provenance import ProvenanceEnvelope
    from improv.oltp.models import Sample
    from improv.plugins import ProvenancePlugin


class ImageService:
    def __init__(
        self,
        store: "ColumnarStore",
        session: "Session",
        parsers: "list[ImageIdParser] | None" = None,
        plugins: "list[ProvenancePlugin] | None" = None,
        storage: "ObjectStore | None" = None,
    ) -> None:
        self._store = store
        self._session = session
        self._parsers: list[ImageIdParser] = parsers or []
        self._plugins: dict[str, ProvenancePlugin] = {
            p.kind: p for p in (plugins or [])
        }
        self._storage = storage

    # ------------------------------------------------------------------
    # Ingest
    # ------------------------------------------------------------------

    def ingest_images(self, records: "list[ImageRecord]") -> None:
        """Write image records to the columnar store."""
        write_images(self._store, records, self._parsers)

    def ingest_provenance(self, records: "list[ProvenanceEnvelope]") -> None:
        """Write provenance records and dual-write plugin index entries.

        Enriches partition key fields (instrument, year, month) on each record
        before writing, so that plugin index records have consistent keys.

        For each record, if a registered plugin handles its kind, calls
        extract_index_record and writes the result to the plugin's index table.
        Records with no registered plugin are stored with no index write.
        """
        from datetime import timezone

        from improv.ids import make_partition_keys

        enriched = []
        for r in records:
            ts = r.timestamp
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            keys = make_partition_keys(
                r.image_id, self._parsers, instrument_hint=r.instrument
            )
            enriched.append(
                r.model_copy(
                    update={
                        "instrument": keys["instrument"],
                        "year": ts.year,
                        "month": ts.month,
                        "timestamp": ts,
                    }
                )
            )

        write_provenance(self._store, enriched, self._parsers)

        for envelope in enriched:
            plugin = self._plugins.get(envelope.kind)
            if plugin is None:
                continue
            index_record = plugin.extract_index_record(envelope)
            if index_record is not None:
                self._store.write(plugin.index_table, [index_record])

    # ------------------------------------------------------------------
    # Retrieval
    # ------------------------------------------------------------------

    def get_image(
        self,
        image_id: str,
        instrument: str | None = None,
    ) -> "ImageRecord | None":
        return get_image(self._store, image_id, self._parsers, instrument)

    def get_provenance(
        self,
        image_id: str,
        kind: str | None = None,
        instrument: str | None = None,
    ) -> "list[ProvenanceEnvelope]":
        if kind is not None:
            return get_provenance_by_kind(
                self._store, image_id, kind, self._parsers, instrument
            )
        return get_provenance(self._store, image_id, self._parsers, instrument)

    def query_images(
        self,
        instrument: str,
        time_start: datetime,
        time_end: datetime,
        lat_min: float | None = None,
        lat_max: float | None = None,
        lon_min: float | None = None,
        lon_max: float | None = None,
    ) -> "list[ImageRecord]":
        """Return images matching time range ± spatial bounding box.

        When spatial bounds are provided, filters via the geolocation index
        and intersects with the time-range result.
        """
        if any(v is not None for v in [lat_min, lat_max, lon_min, lon_max]):
            if None in (lat_min, lat_max, lon_min, lon_max):
                raise ValueError(
                    "All four spatial bounds (lat_min, lat_max, lon_min, lon_max) "
                    "must be provided together."
                )
            geo_ids = set(
                query_spatial(
                    self._store,
                    lat_min,  # type: ignore[arg-type]
                    lat_max,  # type: ignore[arg-type]
                    lon_min,  # type: ignore[arg-type]
                    lon_max,  # type: ignore[arg-type]
                    time_start,
                    time_end,
                )
            )
            return [
                img
                for img in get_images(self._store, instrument, time_start, time_end)
                if img.image_id in geo_ids
            ]

        return list(get_images(self._store, instrument, time_start, time_end))

    # ------------------------------------------------------------------
    # Sample-scoped
    # ------------------------------------------------------------------

    def get_sample(self, sample_id: str) -> "Sample | None":
        from improv.oltp.queries import get_sample
        return get_sample(self._session, sample_id)

    def get_sample_images(self, sample_id: str) -> "list[ImageRecord]":
        """Return all images for a sample, resolved via OLTP time bounds."""
        from improv.oltp.queries import get_sample
        sample = get_sample(self._session, sample_id)
        if sample is None:
            return []
        return list(
            get_images(
                self._store,
                sample.instrument,
                sample.time_start,
                sample.time_end,
            )
        )

    # ------------------------------------------------------------------
    # Dataset-scoped
    # ------------------------------------------------------------------

    def get_dataset_images(self, dataset_name: str) -> "Iterator[ImageRecord]":
        """Yield images for all spans of a named dataset."""
        from improv.oltp.queries import resolve_dataset_to_filters
        for f in resolve_dataset_to_filters(self._session, dataset_name):
            yield from get_images(
                self._store, f["instrument"], f["time_start"], f["time_end"]
            )

    # ------------------------------------------------------------------
    # Binary products
    # ------------------------------------------------------------------

    def get_blob_key(self, image_id: str, instrument: str | None = None) -> str | None:
        """Resolve a storage key for the blob (segmentation mask) of an image.

        Looks up provenance records with kind="blob" and returns the storage_key
        from the most recent record's data payload. Returns None if no blob exists.
        """
        records = self.get_provenance(image_id, kind="blob", instrument=instrument)
        if not records:
            return None
        # Most recent record is authoritative
        latest = max(records, key=lambda r: r.timestamp)
        return latest.data.get("storage_key")
