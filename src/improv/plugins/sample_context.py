"""Sample context provenance plugin.

Handles kind="sample_context". Maintains a sample_index table for
sample-scoped image queries. An image may have multiple sample_index rows
(one per naming scheme or source), enabling multi-ID and late-assignment cases.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import BaseModel

if TYPE_CHECKING:
    from amplify_db_utils import ColumnarStore
    from improv.models.provenance import ProvenanceEnvelope


class SampleContextRecord(BaseModel):
    """Payload schema for sample_context provenance records (goes in data field)."""
    sample_id: str
    source: str  # naming scheme / authority


class SampleIndexRecord(BaseModel):
    """Index record for sample-scoped image queries."""
    image_id: str
    sample_id: str
    source: str
    # Partition keys
    instrument: str | None = None
    year: int | None = None
    month: int | None = None


class SampleContextPlugin:
    kind = "sample_context"
    index_table = "sample_index"
    index_schema = SampleIndexRecord
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
            "sample_id": data["sample_id"],
            "source": data["source"],
            "instrument": envelope.instrument,
            "year": envelope.year,
            "month": envelope.month,
        }
