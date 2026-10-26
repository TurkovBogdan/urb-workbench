"""What a file is attached to — ``attach_file`` and ``delete(FILE@…, holder)`` pick the holder by
its code's prefix, the way ``content_*`` picks a field handler.

``TASK@`` — the task as a whole. ``NOTE@`` — a task note: the file is bound to the note's task and
marked as attached at the note. ``STAGE@`` — likewise at a stage. ``CODEX@`` — a codex note, only
where the mount lets the agent write; a codex itself holds no files. A file is in a task once, so
a note and a stage are spots inside the task, not holders of their own: both lead to the task's
binding.

A holder handler is its type's fence too (``require_visible``) and answers where its code lands
(``locate`` — the task or the codex note) and, for a write, the same with the holder's write rule
asked first (``target``). The registry order is the order the refusal lists the types in.

A target names its holder by code (``holder``) for ``core_storage_upload``, which takes the
bytes — from a path on the server or with an upload token — and hands them to the same holder
through the registry the domain modules fill. A file stored already is bound here, by the
domain's own ``*_attach_existing``: that is no upload.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from src.modules.codex import files as codex_files
from src.modules.codex.constants import CODEX_CODE_PREFIX
from src.modules.codex.crud import codex as codex_crud
from src.modules.codex.crud import note as codex_note_crud
from src.modules.codex.file_owner import note_owner
from src.modules.codex.models import CodexFile
from src.modules.core_storage.dto import Owner
from src.modules.tasks import files as task_files
from src.modules.tasks.codes import tagged
from src.modules.tasks.constants import NOTE_CODE_PREFIX, STAGE_CODE_PREFIX, TASK_CODE_PREFIX
from src.modules.tasks.crud import note as task_note_crud
from src.modules.tasks.crud import stage as stage_crud
from src.modules.tasks.crud import task as task_crud
from src.modules.tasks.file_owner import task_owner
from src.modules.tasks.files import FilePlace
from src.modules.tasks.models.file import TasksFile
from src.modules.workbench.codes import bare_code, code_prefix
from src.modules.workbench.contracts import Fence, by_prefix
from src.modules.workbench.entities.codex import CodexFence, require_writable_note
from src.modules.workbench.entities.codex import code_of as codex_code_of
from src.modules.workbench.entities.tasks import (
    NoteFence,
    StageFence,
    TaskFence,
    require_live_task,
)
from src.modules.workbench.files.places import Place
from src.modules.workspace.models.workspace import Workspace

Binding = TasksFile | CodexFile


class FileTarget(Protocol):
    """Where a file lands: one holder's binding table, with its own write rule."""

    @property
    def owner(self) -> Owner: ...

    @property
    def holder(self) -> str:
        """The holder's code an upload goes to (``TASK@…``, ``NOTE@…``, ``STAGE@…``, ``CODEX@…``)."""
        ...

    def holds(self, place: Place) -> bool: ...

    async def require_writable(self, active: Workspace) -> None: ...

    async def attach_existing(
        self, file_code: str, *, filename: str | None, title: str, description: str
    ) -> Binding: ...


@dataclass(frozen=True)
class TaskTarget:
    task_code: str
    place: FilePlace = field(default_factory=FilePlace)

    @property
    def owner(self) -> Owner:
        return task_owner(self.task_code)

    @property
    def holder(self) -> str:
        if self.place.note_code:
            return f"{NOTE_CODE_PREFIX}@{self.place.note_code}"
        if self.place.stage_code:
            return f"{STAGE_CODE_PREFIX}@{self.place.stage_code}"
        return f"{TASK_CODE_PREFIX}@{self.task_code}"

    def holds(self, place: Place) -> bool:
        return place.task_code == self.task_code

    async def require_writable(self, active: Workspace) -> None:
        await require_live_task(self.task_code)

    async def attach_existing(
        self, file_code: str, *, filename: str | None, title: str, description: str
    ) -> Binding:
        return await task_files.task_file_attach_existing(
            self.task_code,
            file_code,
            filename=filename,
            place=self.place,
            title=title,
            description=description,
        )


@dataclass(frozen=True)
class CodexNoteTarget:
    note_code: str

    @property
    def owner(self) -> Owner:
        return note_owner(self.note_code)

    @property
    def holder(self) -> str:
        return f"{CODEX_CODE_PREFIX}@{self.note_code}"

    def holds(self, place: Place) -> bool:
        return place.codex_note_code == self.note_code

    async def require_writable(self, active: Workspace) -> None:
        await require_writable_note(self.note_code, active)

    async def attach_existing(
        self, file_code: str, *, filename: str | None, title: str, description: str
    ) -> Binding:
        return await codex_files.codex_file_attach_existing(
            self.note_code, file_code, filename=filename, title=title, description=description
        )


class FileHolder(Fence):
    """One holder type: where its code lands, and the target to write to."""

    async def locate(self, bare: str) -> FileTarget:
        """The target the code names, or a refusal saying it does not exist."""
        raise NotImplementedError

    async def target(self, bare: str, active: Workspace) -> FileTarget:
        """The target the code names, once its holder lets the agent write there."""
        found = await self.locate(bare)
        await found.require_writable(active)
        return found


def _missing(prefix: str, bare: str) -> ValueError:
    return ValueError(f"{tagged(prefix, bare)} does not exist.")


class TaskHolder(TaskFence, FileHolder):
    async def locate(self, bare: str) -> FileTarget:
        if await task_crud.task_get(bare, include_deleted=True) is None:
            raise _missing(TASK_CODE_PREFIX, bare)
        return TaskTarget(bare)


class TaskNoteHolder(NoteFence, FileHolder):
    async def locate(self, bare: str) -> FileTarget:
        task_code = await task_note_crud.task_note_task(bare)
        if task_code is None:
            raise _missing(NOTE_CODE_PREFIX, bare)
        return TaskTarget(task_code, FilePlace(note_code=bare))


class StageHolder(StageFence, FileHolder):
    async def locate(self, bare: str) -> FileTarget:
        stage = await stage_crud.stage_get(bare)
        if stage is None:
            raise _missing(STAGE_CODE_PREFIX, bare)
        return TaskTarget(stage.task_code, FilePlace(stage_code=bare))


class CodexNoteHolder(CodexFence, FileHolder):
    async def locate(self, bare: str) -> FileTarget:
        if await codex_crud.codex_get(bare, include_deleted=True) is not None:
            raise ValueError(
                f"{codex_code_of(bare)} is a codex, not a note — files are attached to the notes "
                "inside a codex; codex_get on the codex lists them."
            )
        if await codex_note_crud.note_get(bare, include_deleted=True) is None:
            raise ValueError(f"{codex_code_of(bare)} does not exist.")
        return CodexNoteTarget(bare)


HOLDERS: dict[str, FileHolder] = by_prefix(
    TaskHolder(), TaskNoteHolder(), StageHolder(), CodexNoteHolder()
)


def holder_for(code: str) -> tuple[FileHolder, str]:
    """The holder handler a code names and its bare code, or a refusal saying what to pass."""
    prefix = code_prefix(code)
    handler = HOLDERS.get(prefix)
    if handler is None and not prefix and "/" in code:
        raise ValueError(
            f"{code!r} looks like a codex path — a file goes to a note by its CODEX@ code; "
            f"codex_get([{code!r}]) returns it."
        )
    if handler is None:
        raise ValueError(
            f"{code!r} cannot hold a file — pass a "
            f"{' / '.join(f'{p}@' for p in HOLDERS)} code (CODEX@ — a codex note)."
        )
    return handler, bare_code(code, prefix) or ""


__all__ = [
    "HOLDERS",
    "Binding",
    "CodexNoteTarget",
    "FileHolder",
    "FileTarget",
    "TaskTarget",
    "holder_for",
]
