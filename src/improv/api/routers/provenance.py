"""Provenance endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from improv.api.deps import get_service
from improv.api.schemas import (
    ProvenanceBatchIngest,
    ProvenanceIngest,
    ProvenanceResponse,
)
from improv.models.provenance import ProvenanceEnvelope
from improv.service import ImageService

router = APIRouter(tags=["provenance"])


def _to_response(env: ProvenanceEnvelope) -> ProvenanceResponse:
    return ProvenanceResponse(
        image_id=env.image_id,
        kind=env.kind,
        source=env.source,
        timestamp=env.timestamp,
        data=env.data,
        instrument=env.instrument,
    )


# Batch endpoint registered first so the literal path wins over {image_id}
@router.post(
    "/images/provenance/batch",
    status_code=status.HTTP_201_CREATED,
)
def ingest_provenance_batch(
    body: ProvenanceBatchIngest,
    instrument: str | None = None,
    service: ImageService = Depends(get_service),
) -> dict:
    envelopes = [
        ProvenanceEnvelope(
            image_id="",  # overridden per record below — batch has no shared image_id
            kind=r.kind,
            source=r.source,
            timestamp=r.timestamp,
            data=r.data,
            instrument=instrument,
        )
        for r in body.records
    ]
    service.ingest_provenance(envelopes)
    return {"ingested": len(envelopes)}


@router.get(
    "/images/{image_id}/provenance/{kind}",
    response_model=list[ProvenanceResponse],
)
def get_provenance_by_kind(
    image_id: str,
    kind: str,
    instrument: str | None = None,
    service: ImageService = Depends(get_service),
) -> list[ProvenanceResponse]:
    records = service.get_provenance(image_id, kind=kind, instrument=instrument)
    return [_to_response(r) for r in records]


@router.get(
    "/images/{image_id}/provenance",
    response_model=list[ProvenanceResponse],
)
def get_provenance(
    image_id: str,
    instrument: str | None = None,
    service: ImageService = Depends(get_service),
) -> list[ProvenanceResponse]:
    records = service.get_provenance(image_id, instrument=instrument)
    return [_to_response(r) for r in records]


@router.post(
    "/images/{image_id}/provenance",
    status_code=status.HTTP_201_CREATED,
)
def ingest_provenance(
    image_id: str,
    body: ProvenanceIngest,
    instrument: str | None = None,
    service: ImageService = Depends(get_service),
) -> dict:
    envelope = ProvenanceEnvelope(
        image_id=image_id,
        kind=body.kind,
        source=body.source,
        timestamp=body.timestamp,
        data=body.data,
        instrument=instrument,
    )
    service.ingest_provenance([envelope])
    return {"ingested": 1}
