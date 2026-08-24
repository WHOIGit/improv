"""FastAPI dependency injection helpers."""

from __future__ import annotations

from typing import Iterator

from fastapi import Request

from improv.service import ImageService


def get_service(request: Request) -> Iterator[ImageService]:
    """Yield an ImageService scoped to this request.

    A SQLAlchemy Session is not thread-safe, and every route is a sync ``def``
    that FastAPI runs in a threadpool — so the Session cannot be shared. Worker
    count is irrelevant to this: each worker process would still share one
    Session across its own threadpool.

    The columnar store, parsers, plugins and object store *are* shared
    process-wide (see ``create_app``); only the Session is per-request.
    ``ImageService.__init__`` is cheap enough to build per request.
    """
    state = request.app.state
    session = state.session_factory()
    try:
        yield ImageService(
            store=state.store,
            session=session,
            parsers=state.config.parsers,
            plugins=state.config.plugins,
            storage=state.config.storage,
        )
    finally:
        session.close()
