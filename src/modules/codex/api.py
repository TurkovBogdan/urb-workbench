"""HTTP API of the ``codex`` module (mounted at ``/internal/codex`` — see ``module.py``).

The person's surface: codexes, their trees of notes, and mounting into workspaces. Every rule is
the service's (``crud/``, ``rules.py``); a route only translates:

- a code of a foreign type — 400 (a mixed-up argument, not a missing row);
- no such row — 404 with a code;
- a deleted row asked to change — 409 with a code; a broken tree rule — 409 with the service's
  text, which names the rule and the numbers;
- a note with children asked to go alone — 409 ``codex.note.has_children`` with the children in
  ``params``, so the page can ask the person what to do with them.

**An unknown field in the body is a refusal, not silence** (``extra="forbid"`` on every body).
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Response
from pydantic import BaseModel, ConfigDict, StringConstraints

from src.core.api import ApiError
from src.modules.codex.codes import bare_code
from src.modules.codex.constants import (
    BODY_MAX,
    CODEX_CODE_PREFIX,
    COLOR_MAX,
    DESCRIPTION_MAX,
    FILE_CODE_PREFIX,
    FILE_DESCRIPTION_MAX,
    FILE_TITLE_MAX,
    ICON_MAX,
    SEGMENT_MAX,
    TITLE_MAX,
)
from src.modules.codex import files as codex_files
from src.modules.codex.crud import codex as codex_crud
from src.modules.codex.crud import file as file_crud
from src.modules.codex.crud import mount as mount_crud
from src.modules.codex.crud import note as note_crud
from src.modules.codex.crud.read import codex_branch, note_node, search, subtree
from src.modules.codex.dto import (
    CodexCode,
    CodexRow,
    CodexSummaryRow,
    MountRow,
    NoteFileRow,
    NoteRow,
    TreeNode,
    WorkspaceCodexRow,
)
from src.modules.codex.errors import (
    CODEX_DELETED,
    CODEX_NOT_DELETED,
    CODEX_NOT_FOUND,
    FILE_HOLDER_IS_CODEX,
    FILE_NOT_FOUND,
    MOUNT_NOT_FOUND,
    NOTE_DELETED,
    NOTE_HAS_CHILDREN,
    NOTE_NOT_DELETED,
    NOTE_NOT_FOUND,
    CodexRuleError,
)
from src.modules.codex.models import Codex, CodexNote
from src.modules.workspace.codes import bare_code as workspace_bare_code
from src.modules.workspace.constants import WORKSPACE_CODE_PREFIX
from src.modules.workspace.crud.workspace import workspace_get
from src.modules.workspace.errors import WORKSPACE_NOT_FOUND

router = APIRouter()

Title = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=TITLE_MAX)]
Description = Annotated[str, StringConstraints(strip_whitespace=True, max_length=DESCRIPTION_MAX)]
Body = Annotated[str, StringConstraints(max_length=BODY_MAX)]
Segment = Annotated[str, StringConstraints(strip_whitespace=True, max_length=SEGMENT_MAX)]


class _Body(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CodexBody(_Body):
    """The whole codex as its page saves it.

    The look is the one exception to "whole": the material page saves the text and does not carry
    the look, so ``None`` leaves it as it is. Colour and icon names are not checked against the
    palettes — only the frontend knows how to draw them, as with a workspace.
    """

    segment: Segment
    title: Title
    description: Description = ""
    body: Body = ""
    color: Annotated[str, StringConstraints(max_length=COLOR_MAX)] | None = None
    icon: Annotated[str, StringConstraints(max_length=ICON_MAX)] | None = None


class NoteCreateBody(_Body):
    parent_code: str
    segment: Segment
    title: Title
    description: Description = ""
    body: Body = ""


class NoteBody(_Body):
    """The whole note as its page saves it; its place changes through ``/move``."""

    segment: Segment
    title: Title
    description: Description = ""
    body: Body = ""


class NoteMoveBody(_Body):
    """``parent_code`` — under that codex (its top level) or note; ``after_code`` — right after that
    sibling, ``null`` — first. Left out, each keeps its value: a move lands at the end of the row,
    a place alone does not move."""

    parent_code: str | None = None
    after_code: str | None = None


class MountBody(_Body):
    codex_code: str
    agent_can_edit: bool = True


class MountPatchBody(_Body):
    agent_can_edit: bool


class MountReorderBody(_Body):
    after_code: str | None = None


def _code(value: str) -> str:
    try:
        return bare_code(value, CODEX_CODE_PREFIX) or ""
    except ValueError as error:
        raise ApiError.bad_request(str(error)) from error


def _workspace_code(value: str) -> str:
    try:
        return workspace_bare_code(value, WORKSPACE_CODE_PREFIX) or ""
    except ValueError as error:
        raise ApiError.bad_request(str(error)) from error


def _refused(error: ValueError) -> ApiError:
    return ApiError.conflict(str(error))


async def _require_codex(code: str) -> Codex:
    row = await codex_crud.codex_get(code, include_deleted=True)
    if row is None:
        raise ApiError.not_found("Codex not found", code=CODEX_NOT_FOUND)
    return row


async def _require_note(code: str) -> CodexNote:
    row = await note_crud.note_get(code, include_deleted=True)
    if row is None:
        raise ApiError.not_found("Note not found", code=NOTE_NOT_FOUND)
    return row


async def _require_workspace(code: str) -> None:
    if await workspace_get(code) is None:
        raise ApiError.not_found("Workspace not found", code=WORKSPACE_NOT_FOUND)


async def _note_row(row: CodexNote) -> NoteRow:
    node = await note_node(row.code) if row.deleted_at is None else None
    return NoteRow.model_validate(row).model_copy(update={"path": node.path if node else ""})


# ── codexes ───────────────────────────────────────────────────────────────────


async def _codex_row(row: Codex) -> CodexRow:
    count = (await mount_crud.mount_counts()).get(row.code, 0)
    return CodexRow.model_validate(row).model_copy(update={"mount_count": count})


@router.get("/codexes")
async def list_codexes(include_deleted: bool = False) -> list[CodexSummaryRow]:
    rows = await codex_crud.codex_list(include_deleted=include_deleted)
    counts = await mount_crud.mount_counts()
    return [
        CodexSummaryRow.model_validate(row).model_copy(update={"mount_count": counts.get(row.code, 0)})
        for row in rows
    ]


@router.post("/codexes", status_code=201)
async def create_codex(payload: CodexBody) -> CodexRow:
    try:
        row = await codex_crud.codex_create(**payload.model_dump())
    except ValueError as error:
        raise _refused(error) from error
    return CodexRow.model_validate(row)


@router.get("/codexes/{code}")
async def get_codex(code: str) -> CodexRow:
    """One codex whole — a deleted one too: its state shows in ``deleted_at``."""
    return await _codex_row(await _require_codex(_code(code)))


@router.put("/codexes/{code}")
async def update_codex(code: str, payload: CodexBody) -> CodexRow:
    bare = _code(code)
    if (await _require_codex(bare)).deleted_at is not None:
        raise ApiError.conflict("Codex is deleted — restore it first", code=CODEX_DELETED)
    try:
        row = await codex_crud.codex_update(bare, **payload.model_dump())
    except ValueError as error:
        raise _refused(error) from error
    if row is None:
        raise ApiError.not_found("Codex not found", code=CODEX_NOT_FOUND)
    return await _codex_row(row)


@router.delete("/codexes/{code}", status_code=204)
async def delete_codex(code: str) -> Response:
    """Soft: the codex leaves every canvas with its notes and mounts kept for a restore."""
    if not await codex_crud.codex_delete(_code(code)):
        raise ApiError.not_found("Codex not found", code=CODEX_NOT_FOUND)
    return Response(status_code=204)


@router.post("/codexes/{code}/restore")
async def restore_codex(code: str) -> CodexRow:
    bare = _code(code)
    if (await _require_codex(bare)).deleted_at is None:
        raise ApiError.conflict("Codex is not deleted — nothing to restore", code=CODEX_NOT_DELETED)
    try:
        await codex_crud.codex_restore(bare)
    except ValueError as error:
        raise _refused(error) from error
    return await _codex_row(await _require_codex(bare))


@router.get("/codexes/{code}/trash")
async def get_codex_trash(code: str) -> list[NoteRow]:
    """The codex's deleted notes — each deletion once, by the note it started at; restoring it
    brings back the branch that left with it."""
    bare = _code(code)
    await _require_codex(bare)
    return [await _note_row(row) for row in await note_crud.note_deleted_roots(bare)]


@router.get("/codexes/{code}/tree")
async def get_codex_tree(code: str) -> TreeNode:
    """The codex and its whole tree of live notes, mounted or not."""
    branch = await codex_branch(_code(code))
    if branch is None:
        raise ApiError.not_found("Codex not found", code=CODEX_NOT_FOUND)
    return TreeNode.of(branch)


# ── notes ─────────────────────────────────────────────────────────────────────


@router.post("/notes", status_code=201)
async def create_note(payload: NoteCreateBody) -> NoteRow:
    try:
        row = await note_crud.note_create(
            parent_code=_code(payload.parent_code),
            **payload.model_dump(exclude={"parent_code"}),
        )
    except ValueError as error:
        raise _refused(error) from error
    return await _note_row(row)


@router.get("/notes/{code}")
async def get_note(code: str) -> NoteRow:
    return await _note_row(await _require_note(_code(code)))


@router.put("/notes/{code}")
async def update_note(code: str, payload: NoteBody) -> NoteRow:
    bare = _code(code)
    if (await _require_note(bare)).deleted_at is not None:
        raise ApiError.conflict("Note is deleted — restore it first", code=NOTE_DELETED)
    try:
        row = await note_crud.note_update(bare, **payload.model_dump())
    except ValueError as error:
        raise _refused(error) from error
    if row is None:
        raise ApiError.not_found("Note not found", code=NOTE_NOT_FOUND)
    return await _note_row(row)


@router.post("/notes/{code}/move")
async def move_note(code: str, payload: NoteMoveBody) -> NoteRow:
    bare = _code(code)
    if (await _require_note(bare)).deleted_at is not None:
        raise ApiError.conflict("Note is deleted — restore it first", code=NOTE_DELETED)
    sent = payload.model_fields_set
    try:
        row = await note_crud.note_update(
            bare,
            parent_code=_code(payload.parent_code) if payload.parent_code else None,
            after_code=(
                (_code(payload.after_code) if payload.after_code else None)
                if "after_code" in sent
                else note_crud.KEEP
            ),
        )
    except ValueError as error:
        raise _refused(error) from error
    if row is None:
        raise ApiError.not_found("Note not found", code=NOTE_NOT_FOUND)
    return await _note_row(row)


@router.delete("/notes/{code}", status_code=204)
async def delete_note(code: str, branch: bool = False) -> Response:
    """Soft. A note with live children goes only with ``?branch=true`` — otherwise 409 naming them."""
    try:
        existed = await note_crud.note_delete(_code(code), with_branch=branch)
    except note_crud.NoteHasChildren as error:
        raise ApiError.conflict(
            str(error),
            code=NOTE_HAS_CHILDREN,
            params={
                "count": len(error.children),
                "children": ", ".join(segment for _, segment in error.children),
            },
        ) from error
    if not existed:
        raise ApiError.not_found("Note not found", code=NOTE_NOT_FOUND)
    return Response(status_code=204)


@router.post("/notes/{code}/restore")
async def restore_note(code: str) -> NoteRow:
    bare = _code(code)
    if (await _require_note(bare)).deleted_at is None:
        raise ApiError.conflict("Note is not deleted — nothing to restore", code=NOTE_NOT_DELETED)
    try:
        await note_crud.note_restore(bare)
    except ValueError as error:
        raise _refused(error) from error
    return await _note_row(await _require_note(bare))


# ── note files ────────────────────────────────────────────────────────────────
# The files a codex note holds. Bytes and names are ``core_storage``'s; here the person reads the
# list, re-titles, reorders and detaches. The person uploads through ``core_storage_upload``
# (``POST /storage/upload?holder=CODEX@…``), which answers with ``note_file_row``
# (``file_holders.py``); the agent's tools attach through ``codex.files`` too. A codex itself
# holds no files.


class NoteFilePatchBody(_Body):
    """The fields the page changed — only those."""

    title: Annotated[str, StringConstraints(max_length=FILE_TITLE_MAX)] | None = None
    description: Annotated[str, StringConstraints(max_length=FILE_DESCRIPTION_MAX)] | None = None


class NoteFileOrderBody(_Body):
    """The note's files top to bottom, as the person left them after a drag."""

    codes: list[str]


def _file_code(value: str) -> str:
    try:
        return bare_code(value, FILE_CODE_PREFIX) or ""
    except ValueError as error:
        raise ApiError.bad_request(str(error)) from error


async def _file_holder(code: str, *, live: bool) -> str:
    """The bare code of a note that may hold files; a codex is refused by name, not as missing.

    ``live`` — the files are about to change: the note and its codex must both be live, since a
    soft deletion of either keeps the files as they are for the restore.
    """
    bare = _code(code)
    if await codex_crud.codex_get(bare, include_deleted=True) is not None:
        raise ApiError.bad_request(
            "A codex holds no files — they are attached to the notes inside it",
            code=FILE_HOLDER_IS_CODEX,
        )
    note = await _require_note(bare)
    if live and note.deleted_at is not None:
        raise ApiError.conflict("Note is deleted — restore it first", code=NOTE_DELETED)
    if live and await codex_crud.codex_get(note.codex_code) is None:
        raise ApiError.conflict("Codex is deleted — restore it first", code=CODEX_DELETED)
    return bare


def note_file_row(view: codex_files.CodexFileView) -> NoteFileRow:
    """A file as the note's list shows it — the list's rows and the answer to an upload."""
    binding, stored = view.binding, view.stored
    return NoteFileRow(
        code=binding.file_code,
        note_code=binding.note_code,
        title=binding.title,
        description=binding.description,
        original_filename=view.original_filename,
        original_extension=view.original_extension,
        mime=stored.mime,
        type=stored.type,
        size=stored.size,
        sort=binding.sort,
        created_at=binding.created_at,
        updated_at=binding.updated_at,
    )


async def _file_rows(note: str) -> list[NoteFileRow]:
    return [note_file_row(view) for view in await codex_files.codex_file_views(note)]


@router.get("/notes/{code}/files")
async def list_note_files(code: str) -> list[NoteFileRow]:
    """The note's files top to bottom — of a deleted note too: they are kept for its restore."""
    return await _file_rows(await _file_holder(code, live=False))


def _refuse_control_characters(*, title: str | None = None, description: str | None = None) -> None:
    """The service's rule (``file_crud.refuse_control_characters``), worded for the page."""
    try:
        file_crud.refuse_control_characters(title=title, description=description)
    except CodexRuleError as error:
        raise ApiError.bad_request(str(error), code=error.code, params=error.params) from error


@router.put("/notes/{code}/files/order")
async def reorder_note_files(code: str, payload: NoteFileOrderBody) -> list[NoteFileRow]:
    bare = await _file_holder(code, live=True)
    try:
        await file_crud.codex_file_reorder(bare, [_file_code(value) for value in payload.codes])
    except CodexRuleError as error:
        raise ApiError.bad_request(str(error), code=error.code) from error
    return await _file_rows(bare)


@router.patch("/notes/{code}/files/{file}")
async def update_note_file(code: str, file: str, payload: NoteFilePatchBody) -> NoteFileRow:
    _refuse_control_characters(title=payload.title, description=payload.description)
    bare, file_bare = await _file_holder(code, live=True), _file_code(file)
    try:
        view = await codex_files.codex_file_retitle(
            bare, file_bare, title=payload.title, description=payload.description
        )
    except CodexRuleError as error:
        raise ApiError.conflict(str(error), code=error.code) from error
    except ValueError as error:
        raise ApiError.bad_request(str(error)) from error
    if view is None:
        raise ApiError.not_found("The file is not in this note", code=FILE_NOT_FOUND)
    return note_file_row(view)


@router.delete("/notes/{code}/files/{file}", status_code=204)
async def detach_note_file(code: str, file: str) -> Response:
    """Take the file out of the note. The file itself goes once nothing else holds it."""
    bare = await _file_holder(code, live=True)
    try:
        detached = await codex_files.codex_file_detach(bare, _file_code(file))
    except CodexRuleError as error:
        raise ApiError.conflict(str(error), code=error.code) from error
    if not detached:
        raise ApiError.not_found("The file is not in this note", code=FILE_NOT_FOUND)
    return Response(status_code=204)


# ── mounts ────────────────────────────────────────────────────────────────────


async def _mount_rows(workspace_code: str) -> list[MountRow]:
    counts = await mount_crud.mount_counts()
    return [
        MountRow(
            codex=CodexSummaryRow.model_validate(codex).model_copy(
                update={"mount_count": counts.get(codex.code, 0)}
            ),
            workspace_code=mount.workspace_code,
            sort=mount.sort,
            agent_can_edit=mount.agent_can_edit,
            created_at=mount.created_at,
        )
        for mount, codex in await mount_crud.mount_list(workspace_code)
    ]


async def _mount_row(workspace_code: str, codex_code: str) -> MountRow:
    found = [m for m in await _mount_rows(workspace_code) if m.codex.code == codex_code]
    if not found:
        raise ApiError.not_found("Codex is not mounted here", code=MOUNT_NOT_FOUND)
    return found[0]


@router.get("/workspaces/{workspace}/tree")
async def get_canvas_tree(workspace: str, include_deleted: bool = False) -> list[TreeNode]:
    """The workspace's canvas as one tree — every mounted codex and its notes, as the agent sees it;
    ``include_deleted`` adds the deleted notes in their places, marked ``deleted``."""
    bare = _workspace_code(workspace)
    await _require_workspace(bare)
    branches = await subtree(bare, include_deleted=include_deleted)
    return [TreeNode.of(branch) for branch in branches or []]


@router.get("/workspaces/{workspace}/search")
async def search_canvas(workspace: str, query: str) -> list[CodexCode]:
    """Codes of the canvas records whose title, description or text holds ``query`` in any case —
    the tree's "search the contents too". The tree itself carries no texts, so the depth is
    asked here; the same search the agent's ``codex_search`` runs. An empty query finds nothing."""
    bare = _workspace_code(workspace)
    await _require_workspace(bare)
    if not query.strip():
        return []
    return [hit.node.code for hit in await search(bare, [query]) or []]


@router.get("/workspaces/{workspace}/mounts")
async def list_mounts(workspace: str) -> list[MountRow]:
    """The workspace's canvas: its live mounted codexes in order."""
    bare = _workspace_code(workspace)
    await _require_workspace(bare)
    return await _mount_rows(bare)


@router.post("/workspaces/{workspace}/mounts", status_code=201)
async def add_mount(workspace: str, payload: MountBody) -> MountRow:
    bare, codex = _workspace_code(workspace), _code(payload.codex_code)
    await _require_workspace(bare)
    await _require_codex(codex)
    try:
        await mount_crud.mount_add(codex, bare, agent_can_edit=payload.agent_can_edit)
    except ValueError as error:
        raise _refused(error) from error
    return await _mount_row(bare, codex)


@router.patch("/workspaces/{workspace}/mounts/{code}")
async def patch_mount(workspace: str, code: str, payload: MountPatchBody) -> MountRow:
    bare, codex = _workspace_code(workspace), _code(code)
    if await mount_crud.mount_set_agent_can_edit(codex, bare, payload.agent_can_edit) is None:
        raise ApiError.not_found("Codex is not mounted here", code=MOUNT_NOT_FOUND)
    return await _mount_row(bare, codex)


async def _workspace_codex_rows(
    workspace_code: str, *, include_deleted: bool = False
) -> list[WorkspaceCodexRow]:
    counts = await mount_crud.mount_counts()
    return [
        WorkspaceCodexRow(
            codex=CodexSummaryRow.model_validate(codex).model_copy(
                update={"mount_count": counts.get(codex.code, 0)}
            ),
            mounted=bool(row and row.enabled),
            agent_can_edit=bool(row and row.enabled and row.agent_can_edit),
        )
        for codex, row in await mount_crud.workspace_codexes(
            workspace_code, include_deleted=include_deleted
        )
    ]


@router.get("/workspaces/{workspace}/codexes")
async def list_workspace_codexes(
    workspace: str, include_deleted: bool = False
) -> list[WorkspaceCodexRow]:
    """Every codex in this workspace's order, switched on or not — the order a switch never moves."""
    bare = _workspace_code(workspace)
    await _require_workspace(bare)
    return await _workspace_codex_rows(bare, include_deleted=include_deleted)


@router.post("/workspaces/{workspace}/codexes/{code}/reorder")
async def reorder_workspace_codex(
    workspace: str, code: str, payload: MountReorderBody
) -> list[WorkspaceCodexRow]:
    """Place a codex right after ``after_code`` in this workspace's order (``null`` — first),
    switched on or not."""
    bare, codex = _workspace_code(workspace), _code(code)
    await _require_workspace(bare)
    try:
        order = await mount_crud.mount_reorder(
            codex, bare, after_code=_code(payload.after_code) if payload.after_code else None
        )
    except ValueError as error:
        raise ApiError.bad_request(str(error)) from error
    if order is None:
        raise ApiError.not_found("Codex not found", code=CODEX_NOT_FOUND)
    return await _workspace_codex_rows(bare)


@router.delete("/workspaces/{workspace}/mounts/{code}", status_code=204)
async def remove_mount(workspace: str, code: str) -> Response:
    if not await mount_crud.mount_remove(_code(code), _workspace_code(workspace)):
        raise ApiError.not_found("Codex is not mounted here", code=MOUNT_NOT_FOUND)
    return Response(status_code=204)


__all__ = ["note_file_row", "router"]
