"""Classifier taxonomy + classification-decode endpoints.

Thin routing over existing ImageService methods. No decode/taxonomy business
logic lives here — the service owns it (see ImageService.decode_classification
and register/get_classifier_taxonomy). Decoding always uses a record's own
model_version, never "latest" (which is display / new-work only).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from improv.api.deps import get_service
from improv.api.schemas import (
    DecodedClassificationResponse,
    DecodeRequest,
    TaxonomyCreate,
    TaxonomyResponse,
)
from improv.service import ImageService

router = APIRouter(tags=["classification"])


def _taxonomy_response(tax) -> TaxonomyResponse:
    return TaxonomyResponse(
        classifier=tax.classifier,
        model_version=tax.model_version,
        class_names=tax.class_names,
        created_at=tax.created_at,
    )


# ---------------------------------------------------------------------------
# Taxonomy registration + lookup
# ---------------------------------------------------------------------------

@router.post(
    "/classifiers/{classifier}/taxonomies",
    response_model=TaxonomyResponse,
    status_code=status.HTTP_201_CREATED,
)
def register_taxonomy(
    classifier: str,
    body: TaxonomyCreate,
    service: ImageService = Depends(get_service),
) -> TaxonomyResponse:
    taxonomy, created = service.register_classifier_taxonomy(
        classifier, body.model_version, body.class_names
    )
    if not created:
        raise HTTPException(
            status_code=409,
            detail=f"Taxonomy for {classifier!r}/{body.model_version!r} already exists.",
        )
    return _taxonomy_response(taxonomy)


# Literal /latest registered before /{model_version} so it isn't captured as a
# version (same pattern the provenance router documents).
@router.get(
    "/classifiers/{classifier}/taxonomies/latest",
    response_model=TaxonomyResponse,
)
def get_latest_taxonomy(
    classifier: str,
    service: ImageService = Depends(get_service),
) -> TaxonomyResponse:
    taxonomy = service.get_latest_classifier_taxonomy(classifier)
    if taxonomy is None:
        raise HTTPException(
            status_code=404, detail=f"No taxonomy registered for classifier {classifier!r}."
        )
    return _taxonomy_response(taxonomy)


@router.get(
    "/classifiers/{classifier}/taxonomies/{model_version}",
    response_model=TaxonomyResponse,
)
def get_taxonomy(
    classifier: str,
    model_version: str,
    service: ImageService = Depends(get_service),
) -> TaxonomyResponse:
    taxonomy = service.get_classifier_taxonomy(classifier, model_version)
    if taxonomy is None:
        raise HTTPException(
            status_code=404,
            detail=f"No taxonomy for {classifier!r}/{model_version!r}.",
        )
    return _taxonomy_response(taxonomy)


# ---------------------------------------------------------------------------
# Decoding — (A) stateless, (B) decoded classification read
# ---------------------------------------------------------------------------

def _decode(
    service: ImageService,
    classifier: str,
    model_version: str,
    scores: list[float],
    winner_index: int,
) -> DecodedClassificationResponse:
    """Decode one vector, mapping the service's ValueErrors to HTTP status.

    Pre-checks taxonomy existence (→404) so a missing taxonomy is distinguished
    from a length/range mismatch (→422); decode_classification raises an
    undifferentiated ValueError for all three.
    """
    if service.get_classifier_taxonomy(classifier, model_version) is None:
        raise HTTPException(
            status_code=404,
            detail=f"No taxonomy for {classifier!r}/{model_version!r}.",
        )
    try:
        decoded = service.decode_classification(
            classifier, model_version, scores, winner_index
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return DecodedClassificationResponse(**decoded)


@router.post(
    "/classifiers/{classifier}/decode",
    response_model=DecodedClassificationResponse,
)
def decode(
    classifier: str,
    body: DecodeRequest,
    service: ImageService = Depends(get_service),
) -> DecodedClassificationResponse:
    return _decode(
        service, classifier, body.model_version, body.scores, body.winner_index
    )


@router.get(
    "/images/{image_id}/classification",
    response_model=list[DecodedClassificationResponse],
)
def get_decoded_classification(
    image_id: str,
    kind: str,
    instrument: str | None = None,
    service: ImageService = Depends(get_service),
) -> list[DecodedClassificationResponse]:
    """Read an image's classification-kind provenance, decoded.

    `classifier` is the plugin `kind`. Each record decodes against its OWN
    model_version (from the stored payload), never "latest".
    """
    records = service.get_provenance(image_id, kind=kind, instrument=instrument)
    return [
        _decode(
            service,
            kind,
            r.data["model_version"],
            r.data["scores"],
            r.data["winner_index"],
        )
        for r in records
    ]
