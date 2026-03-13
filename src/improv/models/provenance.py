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
