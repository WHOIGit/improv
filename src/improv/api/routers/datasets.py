"""Dataset endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from improv.api.deps import get_service
from improv.api.schemas import (
    DatasetCreate,
    DatasetResponse,
    DatasetSpanCreate,
    DatasetSpanResponse,
)
from improv.service import ImageService

router = APIRouter(prefix="/datasets", tags=["datasets"])


def _span_response(span) -> DatasetSpanResponse:
    return DatasetSpanResponse(
        span_id=span.span_id,
        instrument=span.instrument,
        time_start=span.time_start,
        time_end=span.time_end,
    )


def _dataset_response(dataset, spans) -> DatasetResponse:
    return DatasetResponse(
        name=dataset.name,
        description=dataset.description,
        spans=[_span_response(s) for s in spans],
    )


@router.post("", response_model=DatasetResponse, status_code=201)
def create_dataset(
    body: DatasetCreate,
    service: ImageService = Depends(get_service),
) -> DatasetResponse:
    dataset, created = service.create_dataset(body.name, body.description)
    if not created:
        raise HTTPException(status_code=409, detail=f"Dataset {body.name!r} already exists.")
    spans = service.get_dataset_spans(dataset.name)
    return _dataset_response(dataset, spans)


@router.get("", response_model=list[DatasetResponse])
def list_datasets(
    service: ImageService = Depends(get_service),
) -> list[DatasetResponse]:
    datasets = service.list_datasets()
    return [
        _dataset_response(ds, service.get_dataset_spans(ds.name))
        for ds in datasets
    ]


@router.get("/{name}", response_model=DatasetResponse)
def get_dataset(
    name: str,
    service: ImageService = Depends(get_service),
) -> DatasetResponse:
    dataset = service.get_dataset(name)
    if dataset is None:
        raise HTTPException(status_code=404, detail=f"Dataset {name!r} not found.")
    spans = service.get_dataset_spans(name)
    return _dataset_response(dataset, spans)


@router.post("/{name}/spans", response_model=list[DatasetSpanResponse], status_code=201)
def add_dataset_spans(
    name: str,
    body: list[DatasetSpanCreate],
    service: ImageService = Depends(get_service),
) -> list[DatasetSpanResponse]:
    try:
        spans = service.add_dataset_spans(
            name,
            [{"instrument": s.instrument, "time_start": s.time_start, "time_end": s.time_end}
             for s in body],
        )
    except ValueError:
        raise HTTPException(status_code=404, detail=f"Dataset {name!r} not found.")
    return [_span_response(s) for s in spans]
