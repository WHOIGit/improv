"""API-layer request/response Pydantic models.

These are distinct from the internal models (ImageRecord, ProvenanceEnvelope)
to give the REST API an independent schema surface.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


# ---------------------------------------------------------------------------
# Images
# ---------------------------------------------------------------------------

class ImageResponse(BaseModel):
    image_id: str
    instrument: str | None
    timestamp: datetime
    year: int | None
    month: int | None
    parent_image_id: str | None = None
    segmentation_run_id: str | None = None
    roi_index: int | None = None
    bbox_x: int | None = None
    bbox_y: int | None = None
    bbox_w: int | None = None
    bbox_h: int | None = None


class ImageIngest(BaseModel):
    image_id: str
    timestamp: datetime
    instrument: str | None = None
    parent_image_id: str | None = None
    segmentation_run_id: str | None = None
    roi_index: int | None = None
    bbox_x: int | None = None
    bbox_y: int | None = None
    bbox_w: int | None = None
    bbox_h: int | None = None


# ---------------------------------------------------------------------------
# Provenance
# ---------------------------------------------------------------------------

class ProvenanceResponse(BaseModel):
    image_id: str
    kind: str
    source: str
    timestamp: datetime
    data: dict
    instrument: str | None = None


class ProvenanceIngest(BaseModel):
    kind: str
    source: str
    timestamp: datetime
    data: dict


class ProvenanceBatchIngest(BaseModel):
    records: list[ProvenanceIngest]


# ---------------------------------------------------------------------------
# Samples
# ---------------------------------------------------------------------------

class SampleResponse(BaseModel):
    sample_id: str
    instrument: str
    time_start: datetime
    time_end: datetime
    quality_flag: int | None
    alternate_sample_id: str | None
    storage_key: str | None
    metadata: dict
