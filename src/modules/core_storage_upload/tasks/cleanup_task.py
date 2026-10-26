"""Hourly removal of the upload requests whose time is over."""

from __future__ import annotations

from src.core.scheduler import CoreTaskBase, TaskContext
from src.modules.core_storage_upload.services.requests import purge_expired_requests


class RequestCleanupTask(CoreTaskBase):
    MODULE = "core_storage_upload"
    CODE = "cleanup"
    NAME = "Upload request cleanup"
    # English fallback text: the UI shows the dictionary translation keyed by (MODULE, CODE).
    DESCRIPTION = (
        "Hourly: removes the upload requests whose lifetime is over — addresses an agent asked "
        "for and never sent a file to."
    )
    SCHEDULE = "10 * * * *"
    TTL = 600

    @staticmethod
    async def handle(ctx: TaskContext) -> None:
        removed = await purge_expired_requests()
        await ctx.info("expired upload requests removed %d", removed)


__all__ = ["RequestCleanupTask"]
