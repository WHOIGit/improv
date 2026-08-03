"""Image endpoints.

GET  /images/{image_id}           → image bytes from object store
GET  /images/{image_id}/metadata  → image record JSON
GET  /images/search               → query images by time/geo/collection
POST /images/ingest               → register image records
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import Response

from improv.api.auth import WRITE, require_scope
from improv.api.deps import get_service
from improv.api.schemas import ImageIngest, ImageResponse
from improv.models.image import ImageRecord
from improv.service import ImageService

router = APIRouter(prefix="/images", tags=["images"])


def _to_response(record: ImageRecord) -> ImageResponse:
    return ImageResponse(**record.model_dump())


# --- Literal paths first (before {image_id} captures them) ---


@router.get("/search", response_model=list[ImageResponse])
def search_images(
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


@router.post(
    "/ingest",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_scope(WRITE))],
)
def ingest_images(
    body: list[ImageIngest] | ImageIngest,
    service: ImageService = Depends(get_service),
) -> dict:
    if isinstance(body, ImageIngest):
        body = [body]
    records = [ImageRecord(**item.model_dump()) for item in body]
    service.ingest_images(records)
    return {"ingested": len(records)}


# --- Parameterized paths ---


@router.get("/{image_id}/metadata", response_model=ImageResponse)
def get_image_metadata(
    image_id: str,
    instrument: str | None = None,
    service: ImageService = Depends(get_service),
) -> ImageResponse:
    record = service.get_image(image_id, instrument=instrument)
    if record is None:
        raise HTTPException(status_code=404, detail=f"Image {image_id!r} not found.")
    return _to_response(record)


@router.get("/{image_id}")
def get_image_data(
    image_id: str,
    service: ImageService = Depends(get_service),
) -> Response:
    """Return the image bytes from the object store."""
    if service._storage is None:
        raise HTTPException(
            status_code=503,
            detail="Object store not configured on this service instance.",
        )

    try:
        data = service._storage.get(image_id)
    except KeyError:
        raise HTTPException(
            status_code=404,
            detail=f"Image data for {image_id!r} not found in object store.",
        )

    return Response(content=bytes(data), media_type="application/octet-stream")
