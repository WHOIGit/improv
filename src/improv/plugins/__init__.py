"""Provenance plugin protocol and built-in plugin exports.

Plugins drive dual-writes when provenance records arrive via the REST API.
Batch producers bypass plugins and own their dual-writes directly.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    import pyarrow as pa
    from amplify_db_utils import ColumnarStore
    from improv.models.provenance import ProvenanceEnvelope


@runtime_checkable
class ProvenancePlugin(Protocol):
    """Protocol for provenance plugins.

    Each plugin handles one provenance kind. When a record of that kind
    arrives via the REST API, the service calls extract_index_record and
    writes the result to the plugin's index table.

    create_index is called at service startup (idempotent).
    """

    kind: str                               # provenance kind this plugin handles
    index_table: str | None                 # db-utils table name for the index; None = no index write
    index_schema: type | pa.Schema | None   # Pydantic model or Arrow schema for index records; None = no index
    partition_by: list[str]

    def create_index(self, store: "ColumnarStore") -> None:
        """Register the index table with the store. Called at startup."""
        ...

    def extract_index_record(
        self, envelope: "ProvenanceEnvelope"
    ) -> dict | None:
        """Extract an index record from a provenance envelope.

        Returns None to skip the index write for this record.
        """
        ...


from improv.plugins.annotation import (
    FullFrameRegion,
    BBoxRegion,
    IFCBCNNClassificationIndexRecord,
    IFCBCNNClassificationPlugin,
    MachineAnnotationRecord,
    RegionDescriptor,
)
from improv.plugins.blob import BlobPlugin, BlobRecord
from improv.plugins.geolocation import GeoLocationIndexRecord, GeoLocationPlugin
from improv.plugins.ifcb_features import (
    IFCBFeaturesIndexRecord,
    IFCBFeaturesPlugin,
    IFCBFeaturesRecord,
)
from improv.plugins.ifcb_id import IFCBImageIdParser
from improv.plugins.sample_context import SampleContextPlugin, SampleIndexRecord

__all__ = [
    "ProvenancePlugin",
    "MachineAnnotationRecord",
    "FullFrameRegion",
    "BBoxRegion",
    "RegionDescriptor",
    "IFCBCNNClassificationPlugin",
    "IFCBCNNClassificationIndexRecord",
    "BlobPlugin",
    "BlobRecord",
    "IFCBFeaturesPlugin",
    "IFCBFeaturesRecord",
    "IFCBFeaturesIndexRecord",
    "GeoLocationPlugin",
    "GeoLocationIndexRecord",
    "SampleContextPlugin",
    "IFCBImageIdParser",
    "SampleIndexRecord",
]
