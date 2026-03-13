"""Image endpoints."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status

from improv.api.deps import get_service
from improv.api.schemas import ImageIngest, ImageResponse
from improv.models.image import ImageRecord
from improv.service import ImageService

router = APIRouter(prefix="/images", tags=["images"])


def _to_response(record: ImageRecord) -> ImageResponse:
    return ImageResponse(**record.model_dump())


@router.get("/{image_id}", response_model=ImageResponse)
def get_image(
    image_id: str,
    instrument: str | None = None,
    service: ImageService = Depends(get_service),
) -> ImageResponse:
    record = service.get_image(image_id, instrument=instrument)
    if record is None:
        raise HTTPException(status_code=404, detail=f"Image {image_id!r} not found.")
    return _to_response(record)


@router.get("", response_model=list[ImageResponse])
def query_images(
    instrument: str | None = None,
    time_start: datetime | None = None,
    time_end: datetime | None = None,
    lat_min: float | None = None,
    lat_max: float | None = None,
    lon_min: float | None = None,
    lon_max: float | None = None,
    collection: str | None = None,
    service: ImageService = Depends(get_service),
) -> list[ImageResponse]:
    if collection is not None:
        return [
            _to_response(img)
            for img in service.get_dataset_images(collection)
        ]

    if instrument is None or time_start is None or time_end is None:
        raise HTTPException(
            status_code=400,
            detail="instrument, time_start, and time_end are required "
                   "(or use collection= for dataset queries).",
        )

    records = service.query_images(
        instrument,
        time_start,
        time_end,
        lat_min=lat_min,
        lat_max=lat_max,
        lon_min=lon_min,
        lon_max=lon_max,
    )
    return [_to_response(r) for r in records]


@router.post("", status_code=status.HTTP_201_CREATED)
def ingest_images(
    body: list[ImageIngest] | ImageIngest,
    service: ImageService = Depends(get_service),
) -> dict:
    if isinstance(body, ImageIngest):
        body = [body]
    records = [ImageRecord(**item.model_dump()) for item in body]
    service.ingest_images(records)
    return {"ingested": len(records)}
