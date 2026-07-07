"""Provenance plugin protocols and built-in (instrument-agnostic) plugin exports.

Plugins drive dual-writes when provenance records arrive via the REST API.
Batch producers bypass plugins and own their dual-writes directly.

Only instrument-agnostic plugins are imported here. Instrument-specific
plugins live in their own subpackages (e.g. ``improv.plugins.ifcb``) and are
NOT imported at core load time — import them explicitly where they are wired
in, so that core can be used without their dependencies present.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from datetime import datetime

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


# ---------------------------------------------------------------------------
# Optional query-capability protocols
#
# A plugin owns not just how its index is written but how it is queried. The
# service discovers these capabilities structurally (isinstance against the
# runtime-checkable protocol) rather than importing concrete plugin classes,
# so the read path stays decoupled from any specific plugin.
# ---------------------------------------------------------------------------

@runtime_checkable
class SpatialQueryPlugin(Protocol):
    """Capability: answer a lat/lon bounding-box query, returning image_ids."""

    def query_spatial(
        self,
        store: "ColumnarStore",
        lat_min: float,
        lat_max: float,
        lon_min: float,
        lon_max: float,
        time_start: "datetime | None" = None,
        time_end: "datetime | None" = None,
    ) -> list[str]:
        ...


@runtime_checkable
class SampleQueryPlugin(Protocol):
    """Capability: resolve a sample_id to its image_ids."""

    def query_by_sample_id(
        self,
        store: "ColumnarStore",
        sample_id: str,
        source: str | None = None,
    ) -> list[str]:
        ...


from improv.plugins.annotation import (
    BBoxRegion,
    FullFrameRegion,
    RegionDescriptor,
)
from improv.plugins.blob import BlobPlugin, BlobRecord
from improv.plugins.classification import (
    MachineClassificationIndexRecord,
    MachineClassificationPlugin,
    MachineClassificationRecord,
)
from improv.plugins.geolocation import (
    GeoLocationIndexRecord,
    GeoLocationPlugin,
    GeoLocationRecord,
)
from improv.plugins.sample_context import (
    SampleContextPlugin,
    SampleContextRecord,
    SampleIndexRecord,
)

__all__ = [
    "ProvenancePlugin",
    "SpatialQueryPlugin",
    "SampleQueryPlugin",
    "FullFrameRegion",
    "BBoxRegion",
    "RegionDescriptor",
    "BlobPlugin",
    "BlobRecord",
    "MachineClassificationPlugin",
    "MachineClassificationIndexRecord",
    "MachineClassificationRecord",
    "GeoLocationPlugin",
    "GeoLocationRecord",
    "GeoLocationIndexRecord",
    "SampleContextPlugin",
    "SampleContextRecord",
    "SampleIndexRecord",
]
