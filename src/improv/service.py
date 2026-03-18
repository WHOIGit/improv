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
    from improv.oltp.models import Dataset, DatasetSpan, Instrument, Sample
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

    def enrich_envelopes(
        self,
        records: "list[ProvenanceEnvelope]",
    ) -> "list[ProvenanceEnvelope]":
        """Return copies of *records* with partition keys (instrument, year, month) filled in.

        Batch producers that call ``plugin.extract_index_record`` directly need
        the same enrichment that ``ingest_provenance`` applies internally.  Call
        this first so that index records have consistent partition keys.
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
        return enriched

    def ingest_provenance(
        self,
        records: "list[ProvenanceEnvelope]",
        write_indexes: bool = True,
    ) -> None:
        """Write provenance records and dual-write plugin index entries.

        Enriches partition key fields (instrument, year, month) on each record
        before writing, so that plugin index records have consistent keys.

        For each record, if a registered plugin handles its kind, calls
        extract_index_record and writes the result to the plugin's index table.
        Records with no registered plugin are stored with no index write.

        Pass ``write_indexes=False`` to skip per-record index writes entirely.
        Batch producers should do so and perform their own batched store.write.
        """
        enriched = self.enrich_envelopes(records)

        write_provenance(self._store, enriched, self._parsers)

        if not write_indexes:
            return

        for envelope in enriched:
            plugin = self._plugins.get(envelope.kind)
            if plugin is None:
                continue
            index_record = plugin.extract_index_record(envelope)
            if index_record is not None and plugin.index_table is not None:
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
    # Instrument registration
    # ------------------------------------------------------------------

    def register_instrument(
        self,
        name: str,
        type: str,
        deployment_start: "datetime",
        serial_number: str | None = None,
        deployment_end: "datetime | None" = None,
        description: str | None = None,
    ) -> "tuple[Instrument, bool]":
        """Register an instrument; return (instrument, created)."""
        from improv.oltp.queries import get_instrument, register_instrument
        existing = get_instrument(self._session, name)
        if existing is not None:
            return existing, False
        instrument = register_instrument(
            self._session, name, type, deployment_start,
            serial_number=serial_number,
            deployment_end=deployment_end,
            description=description,
        )
        self._session.commit()
        return instrument, True

    def get_instrument(self, name: str) -> "Instrument | None":
        from improv.oltp.queries import get_instrument
        return get_instrument(self._session, name)

    # ------------------------------------------------------------------
    # Sample registration
    # ------------------------------------------------------------------

    def register_sample(
        self,
        sample_id: str,
        instrument: str,
        time_start: "datetime",
        time_end: "datetime",
        quality_flag: int | None = None,
        alternate_sample_id: str | None = None,
        storage_key: str | None = None,
        meta: dict | None = None,
    ) -> "tuple[Sample, bool]":
        """Register a sample; return (sample, created)."""
        from improv.oltp.queries import get_sample, register_sample
        existing = get_sample(self._session, sample_id)
        if existing is not None:
            return existing, False
        sample = register_sample(
            self._session, sample_id, instrument, time_start, time_end,
            quality_flag=quality_flag,
            alternate_sample_id=alternate_sample_id,
            storage_key=storage_key,
            meta=meta,
        )
        self._session.commit()
        return sample, True

    def register_samples_batch(
        self,
        records: list[dict],
    ) -> "tuple[int, int]":
        """Register a batch of samples idempotently; return (registered, skipped)."""
        from improv.oltp.queries import get_sample, register_sample
        registered = skipped = 0
        for r in records:
            existing = get_sample(self._session, r["sample_id"])
            if existing is not None:
                skipped += 1
                continue
            register_sample(
                self._session,
                r["sample_id"],
                r["instrument"],
                r["time_start"],
                r["time_end"],
                quality_flag=r.get("quality_flag"),
                alternate_sample_id=r.get("alternate_sample_id"),
                storage_key=r.get("storage_key"),
                meta=r.get("metadata"),
            )
            registered += 1
        if registered:
            self._session.commit()
        return registered, skipped

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

    def create_dataset(
        self, name: str, description: str | None = None
    ) -> "tuple[Dataset, bool]":
        """Create a dataset; return (dataset, created) where created=False if it already existed."""
        from improv.oltp.queries import get_dataset, register_dataset
        existing = get_dataset(self._session, name)
        if existing is not None:
            return existing, False
        dataset = register_dataset(self._session, name, description)
        self._session.commit()
        return dataset, True

    def get_dataset(self, name: str) -> "Dataset | None":
        from improv.oltp.queries import get_dataset
        return get_dataset(self._session, name)

    def list_datasets(self) -> "list[Dataset]":
        from improv.oltp.models import Dataset
        return list(self._session.query(Dataset).all())

    def add_dataset_spans(
        self,
        dataset_name: str,
        spans: "list[dict]",
    ) -> "list[DatasetSpan]":
        """Add one or more spans to an existing dataset.  Raises ValueError if not found."""
        from improv.oltp.queries import add_dataset_span, get_dataset
        if get_dataset(self._session, dataset_name) is None:
            raise ValueError(f"Dataset {dataset_name!r} not found.")
        result = []
        for s in spans:
            result.append(
                add_dataset_span(
                    self._session,
                    dataset_name,
                    s["instrument"],
                    s["time_start"],
                    s["time_end"],
                )
            )
        self._session.commit()
        return result

    def get_dataset_spans(self, dataset_name: str) -> "list[DatasetSpan]":
        from improv.oltp.queries import get_dataset_spans
        return get_dataset_spans(self._session, dataset_name)

    # ------------------------------------------------------------------
    # Binary products
    # ------------------------------------------------------------------

    def get_blob_key(self, image_id: str, instrument: str | None = None) -> str | None:
        """Resolve an object key for the blob (segmentation mask) of an image.

        Looks up provenance records with kind="blob" and returns the object_key
        from the most recent record's data payload. Returns None if no blob exists.
        """
        records = self.get_provenance(image_id, kind="blob", instrument=instrument)
        if not records:
            return None
        # Most recent record is authoritative
        latest = max(records, key=lambda r: r.timestamp)
        return latest.data.get("object_key")
