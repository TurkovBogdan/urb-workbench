"""``WORKSPACE@`` in the lookup — and the one reading of the workspace filter every type shares.

A workspace is the boundary itself, so the ``workspace`` filter does not narrow it: a workspace
quoted in a body is shown whichever one the person works in, as the switcher shows them all.
Its page is the workspaces list — a workspace has none of its own.
"""

from __future__ import annotations

from sqlalchemy import select

from src.core.database import session_scope
from src.modules.core_lookup import WORKSPACE_FILTER, Filters, Miss, Preview, PreviewResult
from src.modules.workspace.codes import strip_prefix
from src.modules.workspace.models.workspace import Workspace

WORKSPACES_PAGE = "/workspaces"


def workspace_filter(filters: Filters) -> str | None:
    """The bare code of the workspace a lookup is narrowed to; ``None`` — not narrowed."""
    return strip_prefix(filters.get(WORKSPACE_FILTER)) or None


async def workspace_preview(codes: list[str], filters: Filters) -> PreviewResult:
    stmt = select(Workspace.code, Workspace.title, Workspace.description, Workspace.deleted_at).where(
        Workspace.code.in_(codes)
    )
    async with session_scope() as s:
        rows = {row.code: row for row in await s.execute(stmt)}
    result: dict[str, Preview | Miss] = {}
    for code in codes:
        row = rows.get(code)
        if row is None:
            result[code] = Miss.NOT_FOUND
        elif row.deleted_at is not None:
            result[code] = Miss.DELETED
        else:
            result[code] = Preview(row.title, row.description, WORKSPACES_PAGE)
    return result


__all__ = ["WORKSPACES_PAGE", "workspace_filter", "workspace_preview"]
