"""Columnar store operations for the provenance table.

The provenance log is append-only. Records are never edited or deleted.

Implementation note — data field JSON round-trip:
db-utils stores dict fields as JSON strings (large_utf8). store.read() returns
data as a string, not a dict. Always call json.loads() before constructing a
ProvenanceEnvelope from a raw row.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from improv.ids import ImageIdParser, make_partition_keys
from improv.models.provenance import ProvenanceEnvelope

if TYPE_CHECKING:
    from amplify_db_utils import ColumnarStore


def _as_utc(ts: datetime) -> datetime:
    if ts.tzinfo is None:
        return ts.replace(tzinfo=timezone.utc)
    return ts


def _enrich(record: dict, parsers: list[ImageIdParser]) -> dict:
    """Populate instrument, year, month partition keys."""
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
    # db-utils auto-serializes dict→JSON for large_utf8 columns on write,
    # but model_dump() may already have a dict here — leave it as-is.
    return r


def _row_to_envelope(row: dict) -> ProvenanceEnvelope:
    """Convert a raw store row to a ProvenanceEnvelope.

    Deserializes the data field from JSON string to dict.
    """
    r = dict(row)
    if isinstance(r.get("data"), str):
        r["data"] = json.loads(r["data"])
    return ProvenanceEnvelope(**r)


def write_provenance(
    store: "ColumnarStore",
    records: list[ProvenanceEnvelope],
    parsers: list[ImageIdParser],
) -> None:
    """Append provenance records to the columnar store."""
    dicts = [_enrich(r.model_dump(), parsers) for r in records]
    store.write("provenance", dicts)


def get_provenance(
    store: "ColumnarStore",
    image_id: str,
    parsers: list[ImageIdParser],
    instrument_hint: str | None = None,
) -> list[ProvenanceEnvelope]:
    """Return all provenance records for an image."""
    keys = make_partition_keys(image_id, parsers, instrument_hint)
    filters: dict = {"image_id": image_id, **keys}
    return [_row_to_envelope(row) for row in store.read("provenance", filters=filters)]


def get_provenance_by_kind(
    store: "ColumnarStore",
    image_id: str,
    kind: str,
    parsers: list[ImageIdParser],
    instrument_hint: str | None = None,
) -> list[ProvenanceEnvelope]:
    """Return provenance records of a specific kind for an image."""
    keys = make_partition_keys(image_id, parsers, instrument_hint)
    filters: dict = {"image_id": image_id, "kind": kind, **keys}
    return [_row_to_envelope(row) for row in store.read("provenance", filters=filters)]
