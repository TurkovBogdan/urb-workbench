"""How a task's codes take a file — for the upload, which asks by code.

A file is in a task once, as the task's owner: a note and a stage are spots inside the task, so
``NOTE@`` and ``STAGE@`` read as the task they belong to.

- **Upload** (``core_storage_upload``): ``TASK@`` takes a file into the task as a whole, ``NOTE@``
  and ``STAGE@`` into their task, marked as attached there; the upload's payload carries the
  file's ``title`` and ``description``. The checks and the binding are this module's
  (``files.py``, ``crud/file.py``). An upload by the agent of a workspace (an upload request, a
  path on the server) goes only to a task of that workspace — asked when the request is opened
  and again when the bytes come, since a request outlives minutes of changes. A
  refusal goes out with its code and the kind of answer it is — a task, note or stage that is not
  there is ``MISSING``, a deleted task is ``CONFLICT``, the same bytes again are ``AlreadyHeld``
  (with the file, its name here and its type), a task of another workspace is ``FORBIDDEN``, the
  rest is ``INVALID``.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from typing import Any

from src.modules.core_storage.dto import SpooledFile
from src.modules.core_storage_upload.dto import AttachedFile, Payload, UploadHolder
from src.modules.core_storage_upload.errors import AlreadyHeld, HolderRefused, RefusalKind
from src.modules.core_storage_upload.services.holders import register_upload_holder
from src.modules.tasks import files as task_files
from src.modules.tasks.api import task_file_row
from src.modules.tasks.codes import strip_prefix, tagged
from src.modules.tasks.constants import NOTE_CODE_PREFIX, STAGE_CODE_PREFIX, TASK_CODE_PREFIX
from src.modules.tasks.crud import file as file_crud
from src.modules.tasks.crud import note as task_note_crud
from src.modules.tasks.crud import stage as stage_crud
from src.modules.tasks.crud import task as task_crud
from src.modules.tasks.errors import (
    FILE_ALREADY_ATTACHED,
    FILE_NOT_FOUND,
    NOTE_NOT_FOUND,
    STAGE_NOT_FOUND,
    TASK_DELETED,
    TASK_NOT_FOUND,
    TaskRuleError,
)
from src.modules.tasks.files import FilePlace

# ``bare -> (task code, place)``: where in which task a holder's code puts a file.
_Locate = Callable[[str], Awaitable[tuple[str, FilePlace]]]

_MISSING = frozenset({TASK_NOT_FOUND, NOTE_NOT_FOUND, STAGE_NOT_FOUND})


async def _in_task(bare: str) -> tuple[str, FilePlace]:
    return bare, FilePlace()


async def _in_note(bare: str) -> tuple[str, FilePlace]:
    task_code = await task_note_crud.task_note_task(bare)
    if task_code is None:
        raise TaskRuleError(
            NOTE_NOT_FOUND, f"Task note {tagged(NOTE_CODE_PREFIX, bare)} does not exist."
        )
    return task_code, FilePlace(note_code=bare)


async def _in_stage(bare: str) -> tuple[str, FilePlace]:
    stage = await stage_crud.stage_get(bare)
    if stage is None:
        raise TaskRuleError(
            STAGE_NOT_FOUND, f"Stage {tagged(STAGE_CODE_PREFIX, bare)} does not exist."
        )
    return stage.task_code, FilePlace(stage_code=bare)


async def _require_in(task_code: str, workspace: str | None) -> None:
    """An upload by a workspace's agent goes to a task of that workspace only."""
    if workspace is None:
        return
    task = await task_crud.task_get(task_code, include_deleted=True)
    if task is None:
        raise TaskRuleError(
            TASK_NOT_FOUND, f"Task {tagged(TASK_CODE_PREFIX, task_code)} does not exist."
        )
    if task.workspace_code != workspace:
        raise HolderRefused(
            f"{tagged(TASK_CODE_PREFIX, task_code)} is in another workspace than the one the "
            "upload was asked from.",
            kind=RefusalKind.FORBIDDEN,
        )


def _kind(code: str | None) -> RefusalKind:
    if code in _MISSING:
        return RefusalKind.MISSING
    if code == TASK_DELETED:
        return RefusalKind.CONFLICT
    return RefusalKind.INVALID


async def _refused(error: ValueError, task_code: str | None) -> HolderRefused:
    if isinstance(error, HolderRefused):
        return error
    code = error.code if isinstance(error, TaskRuleError) else None
    params = dict(error.params) if isinstance(error, TaskRuleError) else {}
    if code == FILE_ALREADY_ATTACHED and task_code is not None:
        held = strip_prefix(str(params.get("file", ""))) or ""
        view = await task_files.task_file_view(task_code, held)
        if view is not None:
            # The page shows which file it is, or quotes it in the text.
            params["name"] = view.binding.title or view.original_filename + view.original_extension
            params["type"] = view.stored.type
            attached = AttachedFile(
                file_code=view.binding.file_code,
                title=view.binding.title,
                description=view.binding.description,
            )
            return AlreadyHeld(str(error), attached=attached, code=code, params=params)
    return HolderRefused(str(error), kind=_kind(code), code=code, params=params)


def _fields(payload: Payload) -> tuple[str, str]:
    """The title and the description the upload asks the task for; anything else is no file
    field of a task and is not read."""
    title, description = payload.get("title", ""), payload.get("description", "")
    if not isinstance(title, str) or not isinstance(description, str):
        raise ValueError("A file's title and description are text.")
    return title, description


def _upload_holder(locate: _Locate) -> UploadHolder:
    async def check(bare: str, payload: Payload, *, workspace: str | None = None) -> None:
        task_code = None
        try:
            title, description = _fields(payload)
            task_code, place = await locate(bare)
            await _require_in(task_code, workspace)
            await file_crud.task_file_check(
                task_code,
                note_code=place.note_code,
                stage_code=place.stage_code,
                title=title,
                description=description,
            )
        except ValueError as error:
            raise await _refused(error, task_code) from error

    async def attach(
        bare: str,
        spooled: SpooledFile,
        payload: Payload,
        *,
        filename: str,
        workspace: str | None = None,
    ) -> AttachedFile:
        task_code = None
        try:
            title, description = _fields(payload)
            task_code, place = await locate(bare)
            await _require_in(task_code, workspace)
            row = await task_files.task_file_attach_spooled(
                task_code,
                spooled,
                filename=filename,
                place=place,
                title=title,
                description=description,
            )
        except ValueError as error:
            raise await _refused(error, task_code) from error
        return AttachedFile(file_code=row.file_code, title=row.title, description=row.description)

    async def answer(bare: str, attached: AttachedFile) -> Mapping[str, Any]:
        task_code, _ = await locate(bare)
        view = await task_files.task_file_view(task_code, attached.file_code)
        if view is None:
            # The file manager deleted it in the moment between: the task does not show it.
            raise HolderRefused(
                "The file is not in this task", kind=RefusalKind.MISSING, code=FILE_NOT_FOUND
            )
        return task_file_row(view).model_dump(mode="json")

    return UploadHolder(check=check, attach=attach, answer=answer)


def register_file_holders() -> None:
    """The upload's registry, from ``configure``: which of the task's codes take a file."""
    register_upload_holder(TASK_CODE_PREFIX, _upload_holder(_in_task))
    register_upload_holder(NOTE_CODE_PREFIX, _upload_holder(_in_note))
    register_upload_holder(STAGE_CODE_PREFIX, _upload_holder(_in_stage))


__all__ = ["register_file_holders"]
