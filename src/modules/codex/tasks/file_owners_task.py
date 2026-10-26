"""Hourly reconciliation of the codex notes' storage owners with their binding rows
(``reconcile.py``) — on the schedule of the tasks' own, for the same reasons
(``tasks/scheduled/file_owners_task.py``)."""

from __future__ import annotations

from src.core.scheduler import CoreTaskBase, TaskContext
from src.modules.codex.reconcile import reconcile_note_owners


class FileOwnersTask(CoreTaskBase):
    MODULE = "codex"
    CODE = "file_owners"
    NAME = "Codex note file owners"
    # English fallback text: the UI shows the dictionary translation keyed by (MODULE, CODE).
    DESCRIPTION = (
        "Hourly: releases the storage owners of codex note files that no binding row holds any "
        "more, and reports bindings whose file the storage counts no owner for."
    )
    SCHEDULE = "30 * * * *"
    TTL = 600

    @staticmethod
    async def handle(ctx: TaskContext) -> None:
        report = await reconcile_note_owners()
        await ctx.info("released %d", report.released)
        for note_code, file_code in report.unheld:
            await ctx.warn("note %s binds %s with no live owner", note_code, file_code)


__all__ = ["FileOwnersTask"]
