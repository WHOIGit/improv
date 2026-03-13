"""ImageRecord — one row per image in the columnar store."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class ImageRecord(BaseModel):
    # Envelope — required for all image types
    image_id: str
    timestamp: datetime

    # Partition keys — required by DuckDB backend; nullable for VAST DB
    instrument: str | None = None
    year: int | None = None
    month: int | None = None

    # Segmentation lineage — nullable; None for IFCB and acquisition frames
    parent_image_id: str | None = None
    segmentation_run_id: str | None = None
    roi_index: int | None = None

    # Bounding box — individual columns for VAST DB predicate pushdown
    bbox_x: int | None = None
    bbox_y: int | None = None
    bbox_w: int | None = None
    bbox_h: int | None = None
