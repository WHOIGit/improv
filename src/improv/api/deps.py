"""FastAPI dependency injection helpers."""

from __future__ import annotations

from fastapi import Request

from improv.service import ImageService


def get_service(request: Request) -> ImageService:
    return request.app.state.service
