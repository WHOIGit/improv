"""Ingest task endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from improv.api.auth import READ, WRITE, require_scope
from improv.api.deps import get_service
from improv.api.schemas import IngestTaskCreate, IngestTaskResponse, IngestTaskUpdate
from improv.service import ImageService

router = APIRouter(prefix="/ingest-tasks", tags=["ingest-tasks"])

VALID_STATUSES = {"pending", "complete", "failed"}


def _task_response(task) -> IngestTaskResponse:
    return IngestTaskResponse(
        task_id=task.task_id,
        instrument=task.instrument,
        status=task.status,
        created_at=task.created_at,
        updated_at=task.updated_at,
    )


@router.post(
    "",
    response_model=IngestTaskResponse,
    status_code=201,
    dependencies=[Depends(require_scope(WRITE))],
)
def register_ingest_task(
    body: IngestTaskCreate,
    service: ImageService = Depends(get_service),
) -> IngestTaskResponse:
    task, created = service.register_ingest_task(
        task_id=body.task_id,
        instrument=body.instrument,
    )
    if not created:
        raise HTTPException(
            status_code=409,
            detail=f"Ingest task {body.task_id!r} already exists (status={task.status!r}).",
        )
    return _task_response(task)


@router.get(
    "/{task_id}",
    response_model=IngestTaskResponse,
    dependencies=[Depends(require_scope(READ))],
)
def get_ingest_task(
    task_id: str,
    service: ImageService = Depends(get_service),
) -> IngestTaskResponse:
    task = service.get_ingest_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail=f"Ingest task {task_id!r} not found.")
    return _task_response(task)


@router.patch(
    "/{task_id}",
    response_model=IngestTaskResponse,
    dependencies=[Depends(require_scope(WRITE))],
)
def update_ingest_task(
    task_id: str,
    body: IngestTaskUpdate,
    service: ImageService = Depends(get_service),
) -> IngestTaskResponse:
    if body.status not in VALID_STATUSES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid status {body.status!r}. Must be one of: {', '.join(sorted(VALID_STATUSES))}.",
        )
    task = service.update_ingest_task(task_id, body.status)
    if task is None:
        raise HTTPException(status_code=404, detail=f"Ingest task {task_id!r} not found.")
    return _task_response(task)


@router.delete(
    "/{task_id}",
    status_code=204,
    dependencies=[Depends(require_scope(WRITE))],
)
def delete_ingest_task(
    task_id: str,
    service: ImageService = Depends(get_service),
) -> None:
    deleted = service.delete_ingest_task(task_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Ingest task {task_id!r} not found.")
