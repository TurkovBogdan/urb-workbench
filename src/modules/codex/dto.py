"""DTOs of the ``codex`` module — what the person's pages receive.

A code goes out as ``CODEX@…`` (``prefixed``: the type word only in JSON). Dates are the core's
``DatetimeUTCStr``. Lists carry no ``body``: a codex's rules and a note's text are read one at a
time, never a page of them at once.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from src.core.utils.date import DatetimeUTCStr
from src.modules.codex.codes import prefixed
from src.modules.codex.constants import CODEX_CODE_PREFIX
from src.modules.codex.crud.read import Branch
from src.modules.workspace.constants import WORKSPACE_CODE_PREFIX

CodexCode = prefixed(CODEX_CODE_PREFIX)
WorkspaceCode = prefixed(WORKSPACE_CODE_PREFIX)


class CodexSummaryRow(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    code: CodexCode
    slug: str
    title: str
    description: str = ""
    sort: int
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
    slug: str
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
    slug: str
    title: str
    description: str = ""
    path: str
    children: list[TreeNode] = []

    @classmethod
    def of(cls, branch: Branch) -> TreeNode:
        row = branch.node.note or branch.node.codex
        return cls(
            code=branch.node.code,
            slug=row.slug,
            title=row.title,
            description=row.description,
            path=branch.node.path,
            children=[cls.of(child) for child in branch.children],
        )


class MountRow(BaseModel):
    """A codex in a workspace's canvas: the codex, its place there, and the agent's right."""

    codex: CodexSummaryRow
    workspace_code: WorkspaceCode
    sort: int
    agent_can_edit: bool
    created_at: DatetimeUTCStr


__all__ = ["CodexCode", "CodexRow", "CodexSummaryRow", "MountRow", "NoteRow", "TreeNode"]
