"""Blob retrieval endpoint."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response

from improv.api.deps import get_service
from improv.service import ImageService

router = APIRouter(prefix="/images", tags=["blobs"])


@router.get("/{image_id}/blob")
def get_blob(
    image_id: str,
    instrument: str | None = None,
    service: ImageService = Depends(get_service),
) -> Response:
    """Return the binary blob (segmentation mask) for an image.

    Resolves the storage key from provenance, then fetches via the object store.
    Returns 404 if no blob provenance record exists.
    Returns 503 if no object store is configured.
    """
    if service._storage is None:
        raise HTTPException(
            status_code=503,
            detail="Object store not configured on this service instance.",
        )

    key = service.get_blob_key(image_id, instrument=instrument)
    if key is None:
        raise HTTPException(
            status_code=404,
            detail=f"No blob found for image {image_id!r}.",
        )

    try:
        data = service._storage.get(key)
    except KeyError:
        raise HTTPException(
            status_code=404,
            detail=f"Blob key {key!r} not found in object store.",
        )

    return Response(content=bytes(data), media_type="application/octet-stream")
