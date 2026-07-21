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

from improv.hashing import canonical_data_hash
from improv.ids import ImageIdParser, make_partition_keys
from improv.models.provenance import ProvenanceEnvelope

# Columns that define provenance-row identity for idempotent read-time dedup.
# Two rows agreeing on all four are the same fact; a retry re-appends an
# identical row that collapses here. `written_at` is deliberately excluded so
# retries (which differ only in write time) are treated as duplicates.
_IDENTITY_KEYS = ("image_id", "kind", "source", "data_hash")

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


def _dedup_identity(rows: list[dict]) -> list[dict]:
    """Collapse rows sharing an identity key, keeping one per identity.

    Backend-neutral (pure Python) so idempotency behaves identically on every
    columnar backend — the append-only WORM stores (VAST DB) and the
    overwrite-capable ones (DuckDB/Parquet) alike. Rows sharing an identity key
    are byte-identical except for `written_at`, so which copy is kept is
    immaterial; first occurrence wins.
    """
    seen: dict[tuple, dict] = {}
    for row in rows:
        key = tuple(row.get(k) for k in _IDENTITY_KEYS)
        if key not in seen:
            seen[key] = row
    return list(seen.values())


def write_provenance(
    store: "ColumnarStore",
    records: list[ProvenanceEnvelope],
    parsers: list[ImageIdParser],
) -> None:
    """Append provenance records to the columnar store.

    Stamps each row with its canonical `data_hash` (identity) and a `written_at`
    timestamp before writing. Writes are append-only; deduplication happens at
    read time via the (image_id, kind, source, data_hash) identity key.
    """
    now = datetime.now(timezone.utc)
    dicts = [_enrich(r.model_dump(), parsers) for r in records]
    for d in dicts:
        d["data_hash"] = canonical_data_hash(d["data"])
        d["written_at"] = now
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
    rows = _dedup_identity(list(store.read("provenance", filters=filters)))
    return [_row_to_envelope(row) for row in rows]


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
    rows = _dedup_identity(list(store.read("provenance", filters=filters)))
    return [_row_to_envelope(row) for row in rows]
