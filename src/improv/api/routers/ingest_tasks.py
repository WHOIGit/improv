"""Ingest task endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from improv.api.deps import get_service
from improv.api.schemas import IngestTaskCreate, IngestTaskResponse, IngestTaskUpdate
from improv.service import ImageService

router = APIRouter(prefix="/ingest-tasks", tags=["ingest-tasks"])


def _task_response(task) -> IngestTaskResponse:
    return IngestTaskResponse(
        task_id=task.task_id,
        instrument=task.instrument,
        status=task.status,
        created_at=task.created_at,
        completed_at=task.completed_at,
    )


@router.post("", response_model=IngestTaskResponse, status_code=201)
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


@router.get("/{task_id}", response_model=IngestTaskResponse)
def get_ingest_task(
    task_id: str,
    service: ImageService = Depends(get_service),
) -> IngestTaskResponse:
    task = service.get_ingest_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail=f"Ingest task {task_id!r} not found.")
    return _task_response(task)


@router.patch("/{task_id}", response_model=IngestTaskResponse)
def update_ingest_task(
    task_id: str,
    body: IngestTaskUpdate,
    service: ImageService = Depends(get_service),
) -> IngestTaskResponse:
    if body.status == "complete":
        task = service.complete_ingest_task(task_id)
    elif body.status == "failed":
        task = service.fail_ingest_task(task_id)
    else:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid status {body.status!r}. Must be 'complete' or 'failed'.",
        )
    if task is None:
        raise HTTPException(status_code=404, detail=f"Ingest task {task_id!r} not found.")
    return _task_response(task)
