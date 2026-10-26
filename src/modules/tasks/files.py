"""Files of a task — the service the agent's tools and the uploads build on.

A file is put into ``core_storage`` and bound to the task here; the module's HTTP routes read,
re-title, reorder and detach. The bytes arrive through ``core_storage_upload``, already spooled
(``task_file_attach_spooled``, called by the holder this module registers there —
``file_holders.py``); a file stored already is bound by its code. Codes are bare on the way in
and out, as in the rest of the module.

**Attaching is two steps in two transactions.** The storage opens a write transaction of its own,
and a nested writer on SQLite waits on the lock until the timeout — so the storage is never called
from inside a ``write_scope`` of ours:

1. every refusal known up front — a dead task, a note or a stage not of this task, an over-long
   title, a file the task holds already, a file of another store — is given before anything is
   written (``task_file_check``);
2. the storage takes the file (or one more owner of a stored file) for the task;
3. the binding row is written, its checks repeated in its own transaction. A refusal there gives the
   storage owner back — unless the task does hold the file: the content was stored already and is
   bound, and that binding needs the owner.

**Detaching** is the reverse: the row goes, then the owner is released. The deletion of a holder —
a purged task, a deleted stage, a purged note — does the same from its CRUD function.

**One operation of a task at a time.** Each of these runs under the task's lock
(``file_owner.task_files_lock``): between the check, the storage and the row nothing else of the
same task can remove the row or release the owner, so a binding row and its live owner stay a
pair. The lock serialises within the backend process — the one process there is. An upload's
bytes arrive before the lock is taken — the upload spools them first: the lock covers the storage
and the row, never the network.

**The same bytes again.** The storage answers a registration of content it holds with the stored
file, and a place that holds it keeps its name. A task already holding that file refuses
(``FILE_ALREADY_ATTACHED``) and nothing changed. A task whose binding stayed while the file
manager deleted the file gets the file back — the registration revived it — and the answer is the
binding as it was, its title and place included.

Storage refusals (``SourceNotFound``, ``UnknownStore``…) go out as they are: they come before any
row of ours.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.modules.core_storage.dto import FileOwner, SpooledFile, StoredFile
from src.modules.core_storage.errors import FileNotFound
from src.modules.core_storage.services.files import file_get, file_get_many
from src.modules.core_storage.services.ownership import file_attach, file_owners_many
from src.modules.core_storage.services.registration import file_register_spooled
from src.modules.tasks.codes import tagged
from src.modules.tasks.constants import FILE_CODE_PREFIX, FILE_STORE
from src.modules.tasks.crud import file as file_crud
from src.modules.tasks.errors import FILE_FOREIGN_STORE, FILE_NOT_STORED, TaskRuleError
from src.modules.tasks.file_owner import release_task_file, task_files_lock, task_owner
from src.modules.tasks.models.file import TasksFile


@dataclass(frozen=True)
class TaskFileView:
    """A file as the task shows it: the binding, the stored bytes, the name it came under here."""

    binding: TasksFile
    stored: StoredFile
    original_filename: str
    original_extension: str


@dataclass(frozen=True)
class FilePlace:
    """Where in the task a file is attached — the task as a whole when both are ``None``."""

    note_code: str | None = None
    stage_code: str | None = None


async def task_file_attach_spooled(
    task_code: str,
    spooled: SpooledFile,
    *,
    filename: str = "",
    place: FilePlace = FilePlace(),
    title: str = "",
    description: str = "",
) -> TasksFile:
    """Store a file ``core_storage.file_spool`` wrote and bind it to the task, at the end of its
    files.

    The bytes were written before this call, OUTSIDE the task's lock: an upload is as slow as the
    client, and the task's other file operations — a detach, a stage deletion, the agent's attach,
    the reconciliation — must not wait on it. Under the lock the checks run, the file is
    registered by the counts the spool made — the bytes not read twice — and bound.
    """
    async with task_files_lock(task_code):
        await _check(task_code, place, title, description)
        hidden = await _hidden_files(task_code)
        stored = await file_register_spooled(
            spooled, store=FILE_STORE, owner=task_owner(task_code), filename=filename
        )
        return await _bind(task_code, stored.code, place, title, description, hidden=hidden)


async def task_file_attach_existing(
    task_code: str,
    file_code: str,
    *,
    filename: str | None = None,
    place: FilePlace = FilePlace(),
    title: str = "",
    description: str = "",
) -> TasksFile:
    """Bind a file the storage already holds — one image in a task and in a codex note is one file.

    ``filename`` — the name the file takes in this task; ``None`` takes the name it came under
    elsewhere (``file_attach``). A deleted file, like an absent one, is refused; so is a file of a
    store other than the tasks' — it would be bound and never served.
    """
    try:
        stored = await file_get(file_code)
    except FileNotFound as error:
        raise TaskRuleError(
            FILE_NOT_STORED, f"No stored file {tagged(FILE_CODE_PREFIX, file_code)}."
        ) from error
    if stored.store != FILE_STORE:
        raise TaskRuleError(
            FILE_FOREIGN_STORE,
            f"{tagged(FILE_CODE_PREFIX, stored.code)} lies in the {stored.store!r} store — "
            f"a task holds files of {FILE_STORE!r} only.",
        )
    async with task_files_lock(task_code):
        await _check(task_code, place, title, description, file_code=stored.code)
        await file_attach(stored.code, task_owner(task_code), filename=filename)
        return await _bind(task_code, stored.code, place, title, description)


async def task_file_detach(task_code: str, file_code: str) -> bool:
    """Take the file out of the task; ``True`` — the task held it. The row goes first, then the
    task's storage owner — the file itself goes once no one holds it."""
    async with task_files_lock(task_code):
        if not await file_crud.task_file_delete(task_code, file_code):
            return False
        await release_task_file(task_code, file_code)
        return True


async def task_file_retitle(
    task_code: str,
    file_code: str,
    *,
    title: str | None = None,
    description: str | None = None,
) -> TaskFileView | None:
    """Change the binding's title and description (``None`` = leave as is).

    ``None`` — the task does not show the file: no binding, or the file manager deleted the file.
    Nothing is written then — an edit of a file the list does not show would land unseen.
    """
    async with task_files_lock(task_code):
        if await task_file_view(task_code, file_code) is None:
            return None
        if await file_crud.task_file_update(
            task_code, file_code, title=title, description=description
        ) is None:
            return None
        return await task_file_view(task_code, file_code)


async def task_file_views(task_code: str) -> list[TaskFileView]:
    """The task's files top to bottom, each with its stored data and the name it came under.

    A file the file manager deleted is left out: for the rest of the code it does not exist, and
    taking it again brings it back, binding and all. Three statements whatever the number of files:
    the rows, the stored files, their owners.
    """
    return await _views(await file_crud.task_file_list(task_code))


async def task_file_view(task_code: str, file_code: str) -> TaskFileView | None:
    row = await file_crud.task_file_get(task_code, file_code)
    if row is None:
        return None
    views = await _views([row])
    return views[0] if views else None


async def _views(rows: list[TasksFile]) -> list[TaskFileView]:
    codes = [row.file_code for row in rows]
    stored = await file_get_many(codes)
    owners = await file_owners_many([code for code in codes if code in stored])
    return [
        _view(row, stored[row.file_code], owners.get(row.file_code, []))
        for row in rows
        if row.file_code in stored
    ]


def _view(row: TasksFile, stored: StoredFile, owners: list[FileOwner]) -> TaskFileView:
    owner = task_owner(row.task_code)
    place = next((p for p in owners if p.owner == owner), None)
    return TaskFileView(
        binding=row,
        stored=stored,
        original_filename=place.original_filename if place else "",
        original_extension=place.original_extension if place else "",
    )


async def _hidden_files(task_code: str) -> frozenset[str]:
    """The task's bound files the file manager deleted — taken before a registration, which may
    bring one of them back."""
    codes = [row.file_code for row in await file_crud.task_file_list(task_code)]
    live = await file_get_many(codes)
    return frozenset(code for code in codes if code not in live)


async def _check(
    task_code: str,
    place: FilePlace,
    title: str,
    description: str,
    *,
    file_code: str | None = None,
) -> None:
    await file_crud.task_file_check(
        task_code,
        file_code=file_code,
        note_code=place.note_code,
        stage_code=place.stage_code,
        title=title,
        description=description,
    )


async def _bind(
    task_code: str,
    file_code: str,
    place: FilePlace,
    title: str,
    description: str,
    *,
    hidden: frozenset[str] = frozenset(),
) -> TasksFile:
    if file_code in hidden:
        revived = await file_crud.task_file_get(task_code, file_code)
        if revived is not None:
            return revived
    try:
        return await file_crud.task_file_create(
            task_code=task_code,
            file_code=file_code,
            note_code=place.note_code,
            stage_code=place.stage_code,
            title=title,
            description=description,
        )
    except Exception:
        if await file_crud.task_file_get(task_code, file_code) is None:
            await release_task_file(task_code, file_code)
        raise


__all__ = [
    "FilePlace",
    "TaskFileView",
    "task_file_attach_existing",
    "task_file_attach_spooled",
    "task_file_detach",
    "task_file_retitle",
    "task_file_view",
    "task_file_views",
]
