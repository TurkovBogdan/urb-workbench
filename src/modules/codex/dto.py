"""DTOs of the ``codex`` module — what the person's pages receive.

A code goes out as ``CODEX@…`` (``prefixed``: the type word only in JSON). Dates are the core's
``DatetimeUTCStr``. Lists carry no ``body``: a codex's rules and a note's text are read one at a
time, never a page of them at once.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from src.core.utils.date import DatetimeUTCStr
from src.modules.codex.codes import prefixed
from src.modules.codex.constants import CODEX_CODE_PREFIX, FILE_CODE_PREFIX, SORT_DEFAULT
from src.modules.codex.crud.read import Branch
from src.modules.workspace.constants import WORKSPACE_CODE_PREFIX

CodexCode = prefixed(CODEX_CODE_PREFIX)
WorkspaceCode = prefixed(WORKSPACE_CODE_PREFIX)
FileCode = prefixed(FILE_CODE_PREFIX)


class CodexSummaryRow(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    code: CodexCode
    segment: str
    title: str
    description: str = ""
    color: str = ""
    icon: str = ""
    sort: int
    # How many live workspaces see this codex — the codex is shared, and an edit lands in all.
    mount_count: int = 0
    created_at: DatetimeUTCStr
    updated_at: DatetimeUTCStr
    deleted_at: DatetimeUTCStr | None = None


class CodexRow(CodexSummaryRow):
    """A codex whole — with its rules."""

    body: str = ""


class NoteRow(BaseModel):
    """A codex note whole, with its place: the codex, the parent and the path from the codex.

    ``path`` is empty for a deleted note or one cut off under a deleted ancestor — it has no
    place in any tree until it is restored.
    """

    model_config = ConfigDict(from_attributes=True)

    code: CodexCode
    codex_code: CodexCode
    parent_code: CodexCode | None = None
    segment: str
    title: str
    description: str = ""
    body: str = ""
    sort: int
    path: str = ""
    created_at: DatetimeUTCStr
    updated_at: DatetimeUTCStr
    deleted_at: DatetimeUTCStr | None = None


class TreeNode(BaseModel):
    """One node of a tree view: enough to draw and to open it, no text."""

    code: CodexCode
    segment: str
    title: str
    description: str = ""
    # The codex's look on its root; a note has none and leaves both empty.
    color: str = ""
    icon: str = ""
    path: str
    # A deleted note — present only in a tree read with its deleted notes; a codex is never one.
    deleted: bool = False
    children: list[TreeNode] = []

    @classmethod
    def of(cls, branch: Branch) -> TreeNode:
        note, codex = branch.node.note, branch.node.codex
        row = note or codex
        return cls(
            code=branch.node.code,
            segment=row.segment,
            title=row.title,
            description=row.description,
            color="" if note else codex.color,
            icon="" if note else codex.icon,
            path=branch.node.path,
            deleted=note is not None and note.deleted_at is not None,
            children=[cls.of(child) for child in branch.children],
        )


class WorkspaceCodexRow(BaseModel):
    """A codex as a workspace orders it: switched on there or not, and the agent's right (false
    while off). The list of these is in the workspace's order, the same for both states."""

    codex: CodexSummaryRow
    mounted: bool
    agent_can_edit: bool


class NoteFileRow(BaseModel):
    """A file in a note's list: the binding, and what the storage knows of the file.

    ``title`` empty — the file is shown under the name it came in with,
    ``original_filename + original_extension``.
    """

    code: FileCode
    note_code: CodexCode
    title: str = ""
    description: str = ""
    original_filename: str = ""
    original_extension: str = ""
    mime: str
    type: str
    size: int
    sort: int = SORT_DEFAULT
    created_at: DatetimeUTCStr
    updated_at: DatetimeUTCStr


class MountRow(BaseModel):
    """A codex in a workspace's canvas: the codex, its place there, and the agent's right."""

    codex: CodexSummaryRow
    workspace_code: WorkspaceCode
    sort: int
    agent_can_edit: bool
    created_at: DatetimeUTCStr


__all__ = [
    "CodexCode",
    "CodexRow",
    "CodexSummaryRow",
    "FileCode",
    "MountRow",
    "NoteFileRow",
    "NoteRow",
    "TreeNode",
    "WorkspaceCodexRow",
]
