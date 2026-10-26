"""``FILE@`` and ``IMAGE@`` in the lookup — one stored file, as a text links it or shows it.

Both words name the same code, so one handler answers for both, registered under each word: the
lookup keys its answer by the code that was asked, and a pill gets its preview under the prefix it
was written with. This module registers them because only it reads both binding tables
(``tasks_file``, ``codex_file``) and knows what a workspace sees of them.

A text shows a file from the storage, wherever it was brought in (the owner's decision): the
miss is the storage's own — the file the public route answers 404 for. No stored file, one outside
the served store, or one whose bytes are gone — ``not_found``; the file deleted by the file manager
or let go by its last holder — ``deleted``. A file no holder here binds is still shown.

What a workspace learns of a file is only what its own places say: the title and description of
the binding visible in the filter's workspace (a task of it, a note of a live codex mounted into
it) — the page's own holder first (``holder`` filter: the task or codex note whose page shows the
code, so the text and its files panel name a file alike), then live before deleted, titled before
untitled — else the name the file came under there. With
no place visible the title is neutral, ``<CODE><ext>``: a name given in another workspace does not
cross into this one, as it does not in the agent's tools. No workspace in the filter is no place
visible either: without a boundary to look through, nothing but the code is shown. A deleted codex
is not seen through its mount, as the tools do not see it (``mount_get``).

The link opens the file (``/storage/public/<CODE>``); it names no holder and no name. The type
(``mime``) is the file's own and goes with every preview, neutral or not: the pill's glyph says
what kind of file it is. ``held`` says the title and description came from the page's own holder:
only those the page may edit.

A batch costs a fixed number of statements: the two binding tables, the mounts, the files and
their owners — one each, whatever the number of codes. The bytes are looked at on disk, one
``stat`` per code, in one thread hop.
"""

from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass

from sqlalchemy import select

from src.core.database import session_scope
from src.modules.codex.constants import CODEX_CODE_PREFIX
from src.modules.codex.file_owner import note_owner
from src.modules.codex.models import Codex, CodexFile, CodexMount, CodexNote
from src.modules.core_lookup import HOLDER_FILTER, Filters, Miss, Preview, PreviewResult
from src.modules.core_storage.dto import FileOwner, Owner, StoredFile
from src.modules.core_storage.services.files import file_get_many, file_path
from src.modules.core_storage.services.ownership import file_owners_many
from src.modules.core_storage_view.constants import PUBLIC_STORE
from src.modules.core_storage_view.services.links import public_file_path
from src.modules.tasks.constants import TASK_CODE_PREFIX
from src.modules.tasks.file_owner import task_owner
from src.modules.tasks.models import TasksTask
from src.modules.tasks.models.file import TasksFile
from src.modules.workspace.lookup import workspace_filter


@dataclass(frozen=True)
class _Bound:
    file_code: str
    owner: Owner
    title: str
    description: str
    deleted: bool
    workspace_code: str | None = None
    codex_code: str | None = None


async def _bindings(codes: list[str], narrowed: str | None) -> tuple[list[_Bound], set[str] | None]:
    """Every binding of the files, tasks first, each in binding order; and the codexes mounted
    into the narrowed workspace (``None`` — not narrowed)."""
    tasks = (
        select(
            TasksFile.file_code,
            TasksFile.task_code,
            TasksFile.title,
            TasksFile.description,
            TasksTask.workspace_code,
            TasksTask.deleted_at.is_not(None).label("deleted"),
        )
        .join(TasksTask, TasksTask.code == TasksFile.task_code)
        .where(TasksFile.file_code.in_(codes))
        .order_by(TasksFile.created_at, TasksFile.task_code)
    )
    notes = (
        select(
            CodexFile.file_code,
            CodexFile.note_code,
            CodexFile.title,
            CodexFile.description,
            CodexNote.codex_code,
            (CodexNote.deleted_at.is_not(None) | Codex.deleted_at.is_not(None)).label("deleted"),
        )
        .join(CodexNote, CodexNote.code == CodexFile.note_code)
        .join(Codex, Codex.code == CodexNote.codex_code)
        .where(CodexFile.file_code.in_(codes))
        .order_by(CodexFile.created_at, CodexFile.note_code)
    )
    async with session_scope() as s:
        bound = [
            _Bound(
                row.file_code,
                task_owner(row.task_code),
                row.title,
                row.description,
                bool(row.deleted),
                workspace_code=row.workspace_code,
            )
            for row in await s.execute(tasks)
        ]
        in_codexes = [
            _Bound(
                row.file_code,
                note_owner(row.note_code),
                row.title,
                row.description,
                bool(row.deleted),
                codex_code=row.codex_code,
            )
            for row in await s.execute(notes)
        ]
        mounted: set[str] | None = None
        if narrowed is not None and in_codexes:
            mounts = (
                select(CodexMount.codex_code)
                .join(Codex, Codex.code == CodexMount.codex_code)
                .where(
                    CodexMount.workspace_code == narrowed,
                    CodexMount.enabled.is_(True),
                    Codex.deleted_at.is_(None),
                    CodexMount.codex_code.in_({row.codex_code for row in in_codexes}),
                )
            )
            mounted = set((await s.execute(mounts)).scalars())
    return bound + in_codexes, mounted


def _visible(bound: _Bound, narrowed: str | None, mounted: set[str] | None) -> bool:
    if narrowed is None:
        return False
    if bound.workspace_code is not None:
        return bound.workspace_code == narrowed
    return mounted is not None and bound.codex_code in mounted


def _neutral(stored: StoredFile) -> str:
    return f"{stored.code}{stored.extension}"


def _name(stored: StoredFile, chosen: _Bound, owners: list[FileOwner]) -> str:
    """The name the file came under at the chosen holder, else the neutral one."""
    place = next((place for place in owners if place.owner == chosen.owner), None)
    if place is not None and (place.original_filename or place.original_extension):
        return place.original_filename + place.original_extension
    return _neutral(stored)


def _bytes_present(files: list[StoredFile]) -> set[str]:
    present = set()
    for stored in files:
        try:
            if os.path.isfile(file_path(stored)):
                present.add(stored.code)
        except OSError:
            continue
    return present


def _holder(filters: Filters) -> Owner | None:
    """The owner the page's own entity binds its files under — a task, a codex note; else ``None``."""
    prefix, _, bare = (filters.get(HOLDER_FILTER) or "").strip().upper().partition("@")
    if not bare:
        return None
    if prefix == TASK_CODE_PREFIX:
        return task_owner(bare)
    if prefix == CODEX_CODE_PREFIX:
        return note_owner(bare)
    return None


def _preview(
    stored: StoredFile, visible: list[_Bound], owners: list[FileOwner], holder: Owner | None
) -> Preview:
    if not visible:
        return Preview(_neutral(stored), "", public_file_path(stored.code), stored.mime)
    # The page's own binding first: the title its files panel shows for the same file.
    chosen = min(visible, key=lambda bound: (bound.owner != holder, bound.deleted, not bound.title))
    return Preview(
        chosen.title or _name(stored, chosen, owners),
        chosen.description,
        public_file_path(stored.code),
        stored.mime,
        held=holder is not None and chosen.owner == holder,
    )


async def file_preview(codes: list[str], filters: Filters) -> PreviewResult:
    narrowed = workspace_filter(filters)
    holder = _holder(filters)
    bindings, mounted = await _bindings(codes, narrowed) if narrowed is not None else ([], None)
    stored = await file_get_many(codes, include_deleted=True)
    owners = await file_owners_many(codes, include_deleted=True)
    served = [
        found for found in stored.values() if found.deleted_at is None and found.store == PUBLIC_STORE
    ]
    present = await asyncio.to_thread(_bytes_present, served)
    by_file: dict[str, list[_Bound]] = {}
    for bound in bindings:
        by_file.setdefault(bound.file_code, []).append(bound)
    result: dict[str, Preview | Miss] = {}
    for code in codes:
        found = stored.get(code)
        if found is None:
            result[code] = Miss.NOT_FOUND
        elif found.deleted_at is not None:
            result[code] = Miss.DELETED
        elif code not in present:
            result[code] = Miss.NOT_FOUND
        else:
            held = by_file.get(code, [])
            visible = [bound for bound in held if _visible(bound, narrowed, mounted)]
            result[code] = _preview(found, visible, owners.get(code, []), holder)
    return result


__all__ = ["file_preview"]
