"""IFCB features provenance plugin.

Handles kind="ifcb_features" — morphometric scalar measurements derived from
IFCB segmentation blobs via ifcb-features. Maintains an ifcb_features_index
wide table (one column per scalar) for fast bulk feature retrieval for ML
training and abundance pipelines.

Batch producers should call extract_index_record per envelope and accumulate
results, then call store.write("ifcb_features_index", batch) once per bin
rather than relying on per-record index writes in ingest_provenance.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import BaseModel

if TYPE_CHECKING:
    from amplify_db_utils import ColumnarStore
    from improv.models.provenance import ProvenanceEnvelope


class IFCBFeaturesRecord(BaseModel):
    """Payload schema for ifcb_features provenance records (goes in data field)."""
    run_id: str
    model_version: str          # e.g. "ifcb-features-v2"
    features: dict[str, float]


class IFCBFeaturesIndexRecord(BaseModel):
    """Wide index record — one row per ROI per pipeline run."""
    image_id: str
    run_id: str
    model_version: str
    # ifcb-features v2 scalar columns (FEATURE_COLUMNS in extract_slim_features.py)
    Area: float | None = None
    Biovolume: float | None = None
    BoundingBox_xwidth: float | None = None
    BoundingBox_ywidth: float | None = None
    ConvexArea: float | None = None
    ConvexPerimeter: float | None = None
    Eccentricity: float | None = None
    EquivDiameter: float | None = None
    Extent: float | None = None
    MajorAxisLength: float | None = None
    MinorAxisLength: float | None = None
    Orientation: float | None = None
    Perimeter: float | None = None
    RepresentativeWidth: float | None = None
    Solidity: float | None = None
    SurfaceArea: float | None = None
    maxFeretDiameter: float | None = None
    minFeretDiameter: float | None = None
    numBlobs: float | None = None
    summedArea: float | None = None
    summedBiovolume: float | None = None
    summedConvexArea: float | None = None
    summedConvexPerimeter: float | None = None
    summedMajorAxisLength: float | None = None
    summedMinorAxisLength: float | None = None
    summedPerimeter: float | None = None
    summedSurfaceArea: float | None = None
    Area_over_PerimeterSquared: float | None = None
    Area_over_Perimeter: float | None = None
    summedConvexPerimeter_over_Perimeter: float | None = None
    # Partition keys
    instrument: str | None = None
    year: int | None = None
    month: int | None = None


class IFCBFeaturesPlugin:
    kind = "ifcb_features"
    index_table = "ifcb_features_index"
    index_schema = IFCBFeaturesIndexRecord
    partition_by = ["instrument", "year", "month"]

    def create_index(self, store: "ColumnarStore") -> None:
        store.create_table(
            self.index_table,
            self.index_schema,
            partition_by=self.partition_by,
        )

    def extract_index_record(self, envelope: "ProvenanceEnvelope") -> dict | None:
        data = envelope.data
        features = data.get("features", {})
        return {
            "image_id": envelope.image_id,
            "run_id": data["run_id"],
            "model_version": data["model_version"],
            **{col: features.get(col) for col in (
                "Area", "Biovolume", "BoundingBox_xwidth", "BoundingBox_ywidth",
                "ConvexArea", "ConvexPerimeter", "Eccentricity", "EquivDiameter",
                "Extent", "MajorAxisLength", "MinorAxisLength", "Orientation",
                "Perimeter", "RepresentativeWidth", "Solidity", "SurfaceArea",
                "maxFeretDiameter", "minFeretDiameter", "numBlobs",
                "summedArea", "summedBiovolume", "summedConvexArea",
                "summedConvexPerimeter", "summedMajorAxisLength",
                "summedMinorAxisLength", "summedPerimeter", "summedSurfaceArea",
                "Area_over_PerimeterSquared", "Area_over_Perimeter",
                "summedConvexPerimeter_over_Perimeter",
            )},
            "instrument": envelope.instrument,
            "year": envelope.year,
            "month": envelope.month,
        }
