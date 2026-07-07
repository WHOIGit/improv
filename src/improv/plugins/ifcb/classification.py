"""IFCB CNN classification plugin — a preset of the generic classifier plugin.

The classification plugin is instrument-agnostic (see
improv.plugins.classification). This module only pins the IFCB CNN kind and
index-table names for back-compat and convenient wiring of IFCB deployments.
"""

from __future__ import annotations

from improv.plugins.classification import (
    MachineClassificationIndexRecord,
    MachineClassificationPlugin,
)

# Back-compat alias — the index schema is the generic narrow winner-index.
IFCBCNNClassificationIndexRecord = MachineClassificationIndexRecord


class IFCBCNNClassificationPlugin(MachineClassificationPlugin):
    """MachineClassificationPlugin preset for IFCB CNN classifier output."""

    def __init__(self) -> None:
        super().__init__(
            kind="ifcb_cnn_classification",
            index_table="ifcb_cnn_classification_index",
        )
