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
        year=env.year,
        month=env.month,
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
            image_id=r.image_id,
            kind=r.kind,
            source=r.source,
            timestamp=r.timestamp,
            data=r.data,
            instrument=instrument,  # uniform fallback hint; parser wins per record
        )
        for r in body.records
    ]

    # A batch is assumed single-instrument. Resolve each record's instrument up
    # front and reject (before any write) if the batch spans more than one, or if
    # a record's image_id neither parses nor has the fallback hint.
    try:
        enriched = service.enrich_envelopes(envelopes)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    instruments = {e.instrument for e in enriched}
    if len(instruments) > 1:
        raise HTTPException(
            status_code=422,
            detail=f"Batch spans multiple instruments {sorted(instruments)}; "
            "post one instrument's records at a time.",
        )

    service.ingest_provenance(enriched)
    return {"ingested": len(enriched)}


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
