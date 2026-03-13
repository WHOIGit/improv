"""Sample endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from improv.api.deps import get_service
from improv.api.schemas import ImageResponse, SampleResponse
from improv.models.image import ImageRecord
from improv.service import ImageService

router = APIRouter(prefix="/samples", tags=["samples"])


def _to_image_response(record: ImageRecord) -> ImageResponse:
    return ImageResponse(**record.model_dump())


@router.get("/{sample_id}", response_model=SampleResponse)
def get_sample(
    sample_id: str,
    service: ImageService = Depends(get_service),
) -> SampleResponse:
    sample = service.get_sample(sample_id)
    if sample is None:
        raise HTTPException(status_code=404, detail=f"Sample {sample_id!r} not found.")
    return SampleResponse(
        sample_id=sample.sample_id,
        instrument=sample.instrument,
        time_start=sample.time_start,
        time_end=sample.time_end,
        quality_flag=sample.quality_flag,
        alternate_sample_id=sample.alternate_sample_id,
        storage_key=sample.storage_key,
        metadata=sample.meta or {},
    )


@router.get("/{sample_id}/images", response_model=list[ImageResponse])
def get_sample_images(
    sample_id: str,
    service: ImageService = Depends(get_service),
) -> list[ImageResponse]:
    records = service.get_sample_images(sample_id)
    return [_to_image_response(r) for r in records]
