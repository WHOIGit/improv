"""Machine classification provenance plugin (instrument-agnostic).

Handles machine-classifier output for any classifier family. Scores are stored
**positionally** (a float vector, no class names); the winning class is an
integer index into that vector. Class names live once per classifier in the
ClassifierTaxonomy registry (OLTP), keyed by (classifier, model_version), and
are used to decode index -> name. See ImageService.decode_classification.

Invariant: the vector order is defined by the taxonomy for the record's
model_version. Any change to the class list/order requires a new model_version,
so historical vectors always decode against their own version.

This plugin maintains a narrow "winner-index" — one row per ROI per classifier
run recording only winner_index and winner_score. The full score vector is NOT
indexed: it lives in the provenance payload (envelope.data.scores) and is
retrievable via get_provenance.

Each classifier family registers its own instance with a distinct kind and
index_table, e.g.::

    MachineClassificationPlugin(kind="ecotaxa_cnn", index_table="ecotaxa_cnn_index")
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import BaseModel

if TYPE_CHECKING:
    from amplify_db_utils import ColumnarStore
    from improv.models.provenance import ProvenanceEnvelope


class MachineClassificationRecord(BaseModel):
    """Payload schema for machine classification provenance records (data field).

    scores is positional — index position is the class id; names come from the
    ClassifierTaxonomy for this (classifier, model_version).
    """
    run_id: str
    model_version: str
    scores: list[float]     # positional class scores, no names
    winner_index: int       # index into scores
    winner_score: float     # == scores[winner_index] (convenience)


class MachineClassificationIndexRecord(BaseModel):
    """Narrow winner-index record — one row per ROI per classifier run."""
    image_id: str
    run_id: str
    model_version: str
    winner_index: int
    winner_score: float
    # Partition keys
    instrument: str | None = None
    year: int | None = None
    month: int | None = None


class MachineClassificationPlugin:
    """Generic classifier plugin. Parameterize kind/index_table per family."""

    def __init__(
        self,
        kind: str = "machine_classification",
        index_table: str = "machine_classification_index",
        partition_by: list[str] | None = None,
    ) -> None:
        self.kind = kind
        self.index_table = index_table
        self.index_schema = MachineClassificationIndexRecord
        self.partition_by = partition_by or [
            "instrument", "model_version", "year", "month"
        ]

    def create_index(self, store: "ColumnarStore") -> None:
        store.create_table(
            self.index_table,
            self.index_schema,
            partition_by=self.partition_by,
        )

    def extract_index_record(self, envelope: "ProvenanceEnvelope") -> dict | None:
        data = envelope.data
        winner_index = data["winner_index"]
        scores = data["scores"]
        if not 0 <= winner_index < len(scores):
            raise ValueError(
                f"winner_index {winner_index} out of range for {len(scores)} scores "
                f"(image_id={envelope.image_id!r})"
            )
        return {
            "image_id": envelope.image_id,
            "run_id": data["run_id"],
            "model_version": data["model_version"],
            "winner_index": winner_index,
            "winner_score": data["winner_score"],
            "instrument": envelope.instrument,
            "year": envelope.year,
            "month": envelope.month,
        }
