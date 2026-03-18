"""Blob provenance plugin.

Handles kind="blob" — segmentation masks and other binary products stored
via amplify-storage-utils. The provenance record payload is a pointer:
an object storage key plus optional metadata (checksum, format, dimensions).

No index table is needed — blob existence is queryable via kind="blob" filter
on the provenance table, and get_blob_key resolves the storage key from the
provenance payload.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import BaseModel

if TYPE_CHECKING:
    from amplify_db_utils import ColumnarStore
    from improv.models.provenance import ProvenanceEnvelope


class BlobRecord(BaseModel):
    """Payload schema for blob provenance records (goes in data field)."""
    object_key: str             # storage-utils key; retrieval via storage.get(key)
    format: str                 # e.g. "png"
    width: int | None = None
    height: int | None = None
    checksum: str | None = None
    model_version: str


class BlobPlugin:
    kind = "blob"
    index_table = None
    index_schema = None
    partition_by = []

    def create_index(self, store: "ColumnarStore") -> None:
        pass  # No index table for blobs

    def extract_index_record(self, envelope: "ProvenanceEnvelope") -> dict | None:
        return None  # Blob existence queried via provenance table; no index write
