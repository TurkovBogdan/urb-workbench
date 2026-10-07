"""Zone router of the core_monitoring module (internal zone, no prefix of its own).

One surface so far — ``/tasks`` (scheduler jobs: list, runs, logs). The module does not set
``internal_router_prefix``, and the aggregator adds no prefix — the path root (``/tasks``) is
spelled out in the sub-router's routes themselves.
"""

from __future__ import annotations

from fastapi import APIRouter

from src.modules.core_monitoring.api.tasks import router as tasks_router

internal_router = APIRouter()
internal_router.include_router(tasks_router, tags=["tasks"])

__all__ = ["internal_router"]
