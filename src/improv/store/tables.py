"""Service-owned table registration.

register_service_tables() is called unconditionally at service startup.
All operations are idempotent — safe to call on every restart.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from improv.models.image import ImageRecord
from improv.models.provenance import ProvenanceEnvelope

if TYPE_CHECKING:
    from amplify_db_utils import ColumnarStore
    from improv.plugins import ProvenancePlugin

_PARTITION_BY = ["instrument", "year", "month"]


def register_service_tables(
    store: "ColumnarStore",
    plugins: "list[ProvenancePlugin] | None" = None,
) -> None:
    """Register all service-owned tables and plugin index tables.

    Must be called before any store read/write. Safe to call on every startup.
    """
    store.create_table("images", ImageRecord, partition_by=_PARTITION_BY)
    store.create_table("provenance", ProvenanceEnvelope, partition_by=_PARTITION_BY)
    for plugin in plugins or []:
        plugin.create_index(store)
