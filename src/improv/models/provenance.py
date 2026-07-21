"""ProvenanceEnvelope — one row per provenance record in the columnar store.

The provenance log is append-only. Records are never edited or deleted.
The service stores and retrieves envelopes without interpreting the data payload.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class ProvenanceEnvelope(BaseModel):
    image_id: str
    kind: str
    source: str
    timestamp: datetime
    data: dict  # stored as JSON string in columnar store; deserialized on read

    # Partition keys — co-partitioned with images table
    instrument: str | None = None
    year: int | None = None
    month: int | None = None

    # Idempotency columns — stamped server-side at write, never client-supplied.
    # data_hash is the RFC 8785 canonical hash of `data` and, together with
    # (image_id, kind, source), defines row identity for read-time dedup.
    # written_at records when the row was appended (audit; retries differ here).
    data_hash: str | None = None
    written_at: datetime | None = None
