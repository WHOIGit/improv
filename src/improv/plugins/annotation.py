"""Annotation provenance plugins.

MachineAnnotationRecord is the shared payload schema for all machine annotation
kinds. Each classifier family gets its own plugin with its own kind and index
table — the index schema (which class columns exist) is classifier-family-specific.

Currently implemented:
  IFCBCNNClassificationPlugin  kind="ifcb_cnn_classification"

human_annotation: stubs (RegionDescriptor, FullFrameRegion, BBoxRegion) are
defined as data classes here for reference. Full plugin implementation deferred
until annotation tool integration (Photic / LabelStudio).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from pydantic import BaseModel

if TYPE_CHECKING:
    from amplify_db_utils import ColumnarStore
    from improv.models.provenance import ProvenanceEnvelope


# ---------------------------------------------------------------------------
# Shared machine annotation payload schema
# ---------------------------------------------------------------------------

class MachineAnnotationRecord(BaseModel):
    """Payload schema for machine annotation provenance records (goes in data field).

    Shared across all classifier families — the kind field on the envelope
    identifies which classifier family produced the record.
    """
    run_id: str
    model_version: str              # e.g. "ecotaxa-cnn-v4"
    scores: dict[str, float]        # class name → score (full distribution)
    winner: str
    winner_score: float


# ---------------------------------------------------------------------------
# Human annotation stubs (no plugin yet)
# ---------------------------------------------------------------------------

@dataclass
class FullFrameRegion:
    """The entire image frame is the annotated region."""
    pass


@dataclass
class BBoxRegion:
    """Axis-aligned bounding box region."""
    x: int
    y: int
    width: int
    height: int


# RegionDescriptor is the union of region types
RegionDescriptor = FullFrameRegion | BBoxRegion


# ---------------------------------------------------------------------------
# IFCB CNN classification plugin
# ---------------------------------------------------------------------------

class IFCBCNNClassificationIndexRecord(BaseModel):
    """Wide index record — one row per ROI per classifier run."""
    image_id: str
    run_id: str
    model_version: str
    winner: str
    winner_score: float
    # --- one column per class score (IFCB CNN taxonomy) ---
    # e.g. Ceratium: float | None = None
    # ... full class list from classifier taxonomy (to be expanded)
    # Partition keys
    instrument: str | None = None
    year: int | None = None
    month: int | None = None


class IFCBCNNClassificationPlugin:
    kind = "ifcb_cnn_classification"
    index_table = "ifcb_cnn_classification_index"
    index_schema = IFCBCNNClassificationIndexRecord
    partition_by = ["instrument", "model_version", "year", "month"]

    def create_index(self, store: "ColumnarStore") -> None:
        store.create_table(
            self.index_table,
            self.index_schema,
            partition_by=self.partition_by,
        )

    def extract_index_record(self, envelope: "ProvenanceEnvelope") -> dict | None:
        data = envelope.data
        scores = data.get("scores", {})
        return {
            "image_id": envelope.image_id,
            "run_id": data["run_id"],
            "model_version": data["model_version"],
            "winner": data["winner"],
            "winner_score": data["winner_score"],
            **scores,
            "instrument": envelope.instrument,
            "year": envelope.year,
            "month": envelope.month,
        }
