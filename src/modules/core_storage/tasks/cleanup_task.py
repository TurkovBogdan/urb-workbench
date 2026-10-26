"""Hourly removal of files marked deleted longer than the term from the module settings, and of
temporary files a process left behind."""

from __future__ import annotations

from datetime import timedelta

from src.core.scheduler import CoreTaskBase, TaskContext
from src.modules.core_storage.constants import TEMP_STALE_SECONDS
from src.modules.core_storage.services.cleanup import purge_expired, purge_temporaries
from src.modules.core_storage.settings import cleanup_after, cleanup_limit


class CleanupTask(CoreTaskBase):
    MODULE = "core_storage"
    CODE = "cleanup"
    NAME = "File cleanup"
    # English fallback text: the UI shows the dictionary translation keyed by (MODULE, CODE).
    DESCRIPTION = (
        "Hourly: removes from disk the files marked deleted longer ago than the term in the "
        "module settings, up to the per-run limit from the same settings, and the temporary "
        "files of uploads left untouched for an hour."
    )
    SCHEDULE = "0 * * * *"
    TTL = 600

    @staticmethod
    async def handle(ctx: TaskContext) -> None:
        report = await purge_expired(cleanup_after(), cleanup_limit())
        temporaries = await purge_temporaries(timedelta(seconds=TEMP_STALE_SECONDS))
        await ctx.info(
            "purged %d, kept %d, bytes left on disk %d, temporary files removed %d",
            report.purged,
            report.kept,
            report.bytes_failed,
            temporaries,
        )


__all__ = ["CleanupTask"]
