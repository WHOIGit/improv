"""Instrument endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from improv.api.auth import WRITE, require_scope
from improv.api.deps import get_service
from improv.api.schemas import InstrumentCreate, InstrumentResponse
from improv.service import ImageService

router = APIRouter(prefix="/instruments", tags=["instruments"])


def _instrument_response(instrument) -> InstrumentResponse:
    return InstrumentResponse(
        name=instrument.name,
        type=instrument.type,
        deployment_start=instrument.deployment_start,
        serial_number=instrument.serial_number,
        deployment_end=instrument.deployment_end,
        description=instrument.description,
    )


@router.post(
    "",
    response_model=InstrumentResponse,
    status_code=201,
    dependencies=[Depends(require_scope(WRITE))],
)
def register_instrument(
    body: InstrumentCreate,
    service: ImageService = Depends(get_service),
) -> InstrumentResponse:
    instrument, created = service.register_instrument(
        name=body.name,
        type=body.type,
        deployment_start=body.deployment_start,
        serial_number=body.serial_number,
        deployment_end=body.deployment_end,
        description=body.description,
    )
    if not created:
        raise HTTPException(status_code=409, detail=f"Instrument {body.name!r} already exists.")
    return _instrument_response(instrument)


@router.get("/{name}", response_model=InstrumentResponse)
def get_instrument(
    name: str,
    service: ImageService = Depends(get_service),
) -> InstrumentResponse:
    instrument = service.get_instrument(name)
    if instrument is None:
        raise HTTPException(status_code=404, detail=f"Instrument {name!r} not found.")
    return _instrument_response(instrument)
