"""Where a ``FILE@`` is held, as the active workspace sees it.

A file has one code in every place it is bound to: a task (its notes and stages are spots inside
the task, not places of their own) or a codex note. Each holder module keeps its own binding table
(``tasks_file``, ``codex_file``), and only this surface reads both — so whether a file is visible
in a workspace is answered here: some binding of it is held by a task of that workspace, or by a
note of a codex mounted (switched on) into it. Bindings anywhere else are neither listed nor
touched.

A task in the bin and its files belong to the workspace still: such a place is listed, and taking
the file out of it is refused the way every write to a deleted task is.

The name a file is shown and copied under here comes from these places too (``name_here``): the
storage keeps one name per owner, and its own choice for a file without one — the earliest owner
anywhere — would show a workspace the name a file was brought under in another. The download
address carries that same name (``download_here``), so the file is saved under it.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.modules.codex import files as codex_files
from src.modules.codex.crud import file as codex_file_crud
from src.modules.codex.crud import mount as mount_crud
from src.modules.codex.crud import note as codex_note_crud
from src.modules.codex.file_owner import note_owner
from src.modules.core_storage.dto import FileOwner, Owner
from src.modules.core_storage_view.services.links import public_download_path
from src.modules.tasks import files as task_files
from src.modules.tasks.codes import tagged
from src.modules.tasks.constants import TASK_CODE_PREFIX
from src.modules.tasks.crud import file as task_file_crud
from src.modules.tasks.crud import task as task_crud
from src.modules.tasks.file_owner import task_owner
from src.modules.workbench.entities.codex import code_of as codex_code_of
from src.modules.workbench.entities.codex import require_writable_note
from src.modules.workbench.entities.tasks import require_live_task
from src.modules.workspace.models.workspace import Workspace


@dataclass(frozen=True)
class Place:
    """One binding of a file: who holds it (``task_code`` or ``codex_note_code``, bare) and what
    the file is called there."""

    file_code: str
    holder: str
    holder_title: str
    holder_deleted: bool
    title: str
    description: str
    task_code: str | None = None
    codex_note_code: str | None = None

    @property
    def owner(self) -> Owner:
        """The storage owner this binding stands for."""
        if self.task_code is not None:
            return task_owner(self.task_code)
        return note_owner(self.codex_note_code or "")

    def listed(self) -> str:
        """The place as a refusal names it: the holder's code and title."""
        mark = ", deleted" if self.holder_deleted else ""
        return f"{self.holder} ({self.holder_title!r}{mark})"

    async def require_detachable(self, active: Workspace) -> None:
        """May the agent take the file out of here — the holder's own write rule."""
        if self.task_code is not None:
            await require_live_task(self.task_code)
        else:
            await require_writable_note(self.codex_note_code or "", active)

    async def detach(self) -> bool:
        if self.task_code is not None:
            return await task_files.task_file_detach(self.task_code, self.file_code)
        return await codex_files.codex_file_detach(self.codex_note_code or "", self.file_code)


async def bound_anywhere(file_code: str) -> bool:
    """Whether any holder at all binds the file — in this workspace or another."""
    return bool(
        await task_file_crud.task_file_list_by_file(file_code)
        or await codex_file_crud.codex_file_list_by_file(file_code)
    )


async def visible_places(file_code: str, active: Workspace) -> list[Place]:
    """The file's bindings visible in ``active``: the tasks first, then the codex notes, each in
    the order they were bound."""
    places: list[Place] = []
    for row in await task_file_crud.task_file_list_by_file(file_code):
        task = await task_crud.task_get(row.task_code, include_deleted=True)
        if task is None or task.workspace_code != active.code:
            continue
        places.append(
            Place(
                file_code=file_code,
                holder=tagged(TASK_CODE_PREFIX, task.code) or "",
                holder_title=task.title,
                holder_deleted=task.deleted_at is not None,
                title=row.title,
                description=row.description,
                task_code=task.code,
            )
        )
    for row in await codex_file_crud.codex_file_list_by_file(file_code):
        note = await codex_note_crud.note_get(row.note_code, include_deleted=True)
        if note is None or await mount_crud.mount_get(note.codex_code, active.code) is None:
            continue
        places.append(
            Place(
                file_code=file_code,
                holder=codex_code_of(note.code),
                holder_title=note.title,
                holder_deleted=note.deleted_at is not None,
                title=row.title,
                description=row.description,
                codex_note_code=note.code,
            )
        )
    return places


def name_here(places: list[Place], owners: list[FileOwner]) -> str | None:
    """The name the file came under at the first of ``places`` that brought one; ``None`` — none
    of them did. ``owners`` — the file's storage owners, released ones too."""
    named = _named(owners)
    return next((named[place.owner] for place in places if place.owner in named), None)


def download_here(file_code: str, places: list[Place], owners: list[FileOwner]) -> str:
    """The address that saves the file under the name shown here (``name_here``); no name here —
    under its code."""
    return public_download_path(file_code, name_here(places, owners) or "")


def _named(owners: list[FileOwner]) -> dict[Owner, str]:
    return {
        owner.owner: owner.original_filename + owner.original_extension
        for owner in owners
        if owner.original_filename or owner.original_extension
    }


__all__ = ["Place", "bound_anywhere", "download_here", "name_here", "visible_places"]
