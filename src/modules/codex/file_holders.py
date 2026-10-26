"""How ``CODEX@`` takes a file — for the upload, which asks by code.

Only a codex note holds files; the code of a codex itself is shared by the same prefix and holds
none.

- **Upload** (``core_storage_upload``): a live note of a live codex takes the file. The checks and
  the binding are this module's (``files.py``, ``crud/file.py``); the upload's payload carries the
  file's ``title`` and ``description``. An upload by the agent of a workspace (an upload request,
  a path on the server) goes only to a note whose codex the mount of that workspace lets the
  agent write (``rules.agent_may_write``) — asked when the request is opened and again when the
  bytes come, since a mount may lose the right in between; the person's page
  needs no mount. A refusal goes out with its code and the kind of answer it is — a note that is
  not there is ``MISSING``, a deleted note or codex is ``CONFLICT``, the same bytes again are
  ``AlreadyHeld`` (the file, its name here and its type in ``params``), a codex the agent may not
  write is ``FORBIDDEN``, the rest — a codex's code among them — is ``INVALID``.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from src.modules.codex import files as codex_files
from src.modules.codex.api import note_file_row
from src.modules.codex.codes import strip_prefix, tagged
from src.modules.codex.constants import CODEX_CODE_PREFIX
from src.modules.codex.crud import file as file_crud
from src.modules.codex.crud import mount as mount_crud
from src.modules.codex.crud import note as note_crud
from src.modules.codex.errors import (
    CODEX_DELETED,
    FILE_ALREADY_ATTACHED,
    FILE_NOT_FOUND,
    NOTE_DELETED,
    NOTE_NOT_FOUND,
    CodexRuleError,
)
from src.modules.codex.rules import agent_may_write
from src.modules.core_storage.dto import SpooledFile
from src.modules.core_storage_upload.dto import AttachedFile, Payload, UploadHolder
from src.modules.core_storage_upload.errors import AlreadyHeld, HolderRefused, RefusalKind
from src.modules.core_storage_upload.services.holders import register_upload_holder

_CONFLICT = frozenset({NOTE_DELETED, CODEX_DELETED})


async def _require_writable(note_code: str, workspace: str | None) -> None:
    """An upload by a workspace's agent goes where that workspace's mount lets it write.
    Asked after the note's own checks: the note is there and live by then."""
    if workspace is None:
        return
    note = await note_crud.note_get(note_code)
    mount = await mount_crud.mount_get(note.codex_code, workspace) if note else None
    if mount is None:
        raise HolderRefused(
            f"{tagged(CODEX_CODE_PREFIX, note_code)} is not in a codex mounted into the "
            "workspace the upload was asked from.",
            kind=RefusalKind.FORBIDDEN,
        )
    if not agent_may_write(mount):
        raise HolderRefused(
            f"The codex of {tagged(CODEX_CODE_PREFIX, note_code)} is not editable for you in the "
            "workspace the upload was asked from — writing is switched off in its mount.",
            kind=RefusalKind.FORBIDDEN,
        )


def _kind(code: str | None) -> RefusalKind:
    if code == NOTE_NOT_FOUND:
        return RefusalKind.MISSING
    if code in _CONFLICT:
        return RefusalKind.CONFLICT
    return RefusalKind.INVALID


async def _refused(error: ValueError, note_code: str) -> HolderRefused:
    if isinstance(error, HolderRefused):
        return error
    code = error.code if isinstance(error, CodexRuleError) else None
    params = dict(error.params) if isinstance(error, CodexRuleError) else {}
    if code == FILE_ALREADY_ATTACHED:
        held = strip_prefix(str(params.get("file", ""))) or ""
        view = await codex_files.codex_file_view(note_code, held)
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
    """The title and the description the upload asks the note for; anything else is no file
    field of a note and is not read."""
    title, description = payload.get("title", ""), payload.get("description", "")
    if not isinstance(title, str) or not isinstance(description, str):
        raise ValueError("A file's title and description are text.")
    return title, description


async def _check(bare: str, payload: Payload, *, workspace: str | None = None) -> None:
    try:
        title, description = _fields(payload)
        await file_crud.codex_file_check(bare, title=title, description=description)
        await _require_writable(bare, workspace)
    except ValueError as error:
        raise await _refused(error, bare) from error


async def _attach(
    bare: str,
    spooled: SpooledFile,
    payload: Payload,
    *,
    filename: str,
    workspace: str | None = None,
) -> AttachedFile:
    try:
        title, description = _fields(payload)
        if workspace is not None:
            await file_crud.codex_file_check(bare, title=title, description=description)
            await _require_writable(bare, workspace)
        row = await codex_files.codex_file_attach_spooled(
            bare, spooled, filename=filename, title=title, description=description
        )
    except ValueError as error:
        raise await _refused(error, bare) from error
    return AttachedFile(file_code=row.file_code, title=row.title, description=row.description)


async def _answer(bare: str, attached: AttachedFile) -> Mapping[str, Any]:
    view = await codex_files.codex_file_view(bare, attached.file_code)
    if view is None:
        # The file manager deleted it in the moment between: the note does not show it.
        raise HolderRefused(
            "The file is not in this note", kind=RefusalKind.MISSING, code=FILE_NOT_FOUND
        )
    return note_file_row(view).model_dump(mode="json")


def register_file_holders() -> None:
    """The upload's registry, from ``configure``: which code takes a file."""
    register_upload_holder(
        CODEX_CODE_PREFIX, UploadHolder(check=_check, attach=_attach, answer=_answer)
    )


__all__ = ["register_file_holders"]
