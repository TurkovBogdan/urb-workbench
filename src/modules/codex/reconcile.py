"""The reconciliation of the codex notes' storage owners with their binding rows.

The rules are the tasks' (``tasks/reconcile.py``), for owners ``("CODEX", <note code>, "")``: a
live owner with no ``codex_file`` row is released under the note's file lock, after the row is
looked for again inside it, and only when it was taken longer than ``FILE_OWNER_GRACE`` ago — an
attach in flight in another process is not held off by this process's lock; a row whose file is
live and whose owner is not is reported and left as it is. Soft-deleted notes and codexes keep
their rows, and with them their owners.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.core.loggers import get_logger
from src.core.utils.date import utc_now
from src.modules.codex.constants import CODEX_CODE_PREFIX, FILE_OWNER_GRACE
from src.modules.codex.crud import file as file_crud
from src.modules.codex.file_owner import note_files_lock
from src.modules.core_storage.errors import FileNotFound
from src.modules.core_storage.services.files import file_get_many
from src.modules.core_storage.services.ownership import file_release, held_by_type

_LOG = get_logger("codex")


@dataclass(frozen=True)
class OwnerReconcileReport:
    released: int
    """Live owners with no binding row, released."""

    unheld: list[tuple[str, str]]
    """``(note_code, file_code)`` of rows whose file is live and whose owner is not — reported."""


async def reconcile_note_owners() -> OwnerReconcileReport:
    settled = utc_now() - FILE_OWNER_GRACE
    bound = await file_crud.codex_file_pairs()
    released = 0
    for place in await held_by_type(CODEX_CODE_PREFIX, taken_before=settled):
        note_code = place.owner.id
        if (note_code, place.file_code) in bound:
            continue
        async with note_files_lock(note_code):
            if await file_crud.codex_file_get(note_code, place.file_code) is not None:
                continue
            try:
                if not await file_release(place.file_code, place.owner):
                    continue
            except FileNotFound:
                continue
        released += 1
        _LOG.info("codex: released %s of note %s — no binding row held it", place.file_code, note_code)
    return OwnerReconcileReport(released=released, unheld=await _unheld())


async def _unheld() -> list[tuple[str, str]]:
    held = {(place.owner.id, place.file_code) for place in await held_by_type(CODEX_CODE_PREFIX)}
    missing = sorted(pair for pair in await file_crud.codex_file_pairs() if pair not in held)
    live = await file_get_many([file_code for _, file_code in missing])
    unheld = [pair for pair in missing if pair[1] in live]
    for note_code, file_code in unheld:
        _LOG.warning(
            "codex: note %s binds %s and the storage counts no owner for it — left as is",
            note_code,
            file_code,
        )
    return unheld


__all__ = ["OwnerReconcileReport", "reconcile_note_owners"]
