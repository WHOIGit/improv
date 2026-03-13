"""Sample endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from improv.api.deps import get_service
from improv.api.schemas import (
    BatchRegisterResponse,
    ImageResponse,
    SampleCreate,
    SampleResponse,
)
from improv.models.image import ImageRecord
from improv.service import ImageService

router = APIRouter(prefix="/samples", tags=["samples"])


def _to_image_response(record: ImageRecord) -> ImageResponse:
    return ImageResponse(**record.model_dump())


def _sample_response(sample) -> SampleResponse:
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


@router.post("", response_model=SampleResponse, status_code=201)
def register_sample(
    body: SampleCreate,
    service: ImageService = Depends(get_service),
) -> SampleResponse:
    sample, created = service.register_sample(
        sample_id=body.sample_id,
        instrument=body.instrument,
        time_start=body.time_start,
        time_end=body.time_end,
        quality_flag=body.quality_flag,
        alternate_sample_id=body.alternate_sample_id,
        storage_key=body.storage_key,
        meta=body.metadata,
    )
    if not created:
        raise HTTPException(status_code=409, detail=f"Sample {body.sample_id!r} already exists.")
    return _sample_response(sample)


@router.post("/batch", response_model=BatchRegisterResponse)
def register_samples_batch(
    body: list[SampleCreate],
    service: ImageService = Depends(get_service),
) -> BatchRegisterResponse:
    records = [
        {
            "sample_id": s.sample_id,
            "instrument": s.instrument,
            "time_start": s.time_start,
            "time_end": s.time_end,
            "quality_flag": s.quality_flag,
            "alternate_sample_id": s.alternate_sample_id,
            "storage_key": s.storage_key,
            "metadata": s.metadata,
        }
        for s in body
    ]
    registered, skipped = service.register_samples_batch(records)
    return BatchRegisterResponse(registered=registered, skipped=skipped)


@router.get("/{sample_id}", response_model=SampleResponse)
def get_sample(
    sample_id: str,
    service: ImageService = Depends(get_service),
) -> SampleResponse:
    sample = service.get_sample(sample_id)
    if sample is None:
        raise HTTPException(status_code=404, detail=f"Sample {sample_id!r} not found.")
    return _sample_response(sample)


@router.get("/{sample_id}/images", response_model=list[ImageResponse])
def get_sample_images(
    sample_id: str,
    service: ImageService = Depends(get_service),
) -> list[ImageResponse]:
    records = service.get_sample_images(sample_id)
    return [_to_image_response(r) for r in records]
