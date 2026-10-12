"""``CODEX@`` in the lookup — a codex and a codex note under one prefix.

A code is looked up among codexes first, then among notes; a note answers for its codex in
everything but its own title. Settled in this order: no row — ``not_found``; the codex not mounted
into the filter's workspace — ``foreign_scope``; the codex or the note deleted — ``deleted``.

**Visibility is the mount.** A codex belongs to no workspace: it is visible in the ones it is
mounted into, and a mount switched off (``enabled`` false) shows nothing — the same canvas the
agent reads. Without a workspace filter nothing is narrowed.

Both a codex and a note open the codex materials on that node — one address for either.
"""

from __future__ import annotations

from sqlalchemy import select

from src.core.database import session_scope
from src.modules.codex.codes import tagged
from src.modules.codex.constants import CODEX_CODE_PREFIX
from src.modules.codex.models import Codex, CodexMount, CodexNote
from src.modules.core_lookup import Filters, Miss, Preview, PreviewResult
from src.modules.workspace.lookup import workspace_filter


def materials_page(code: str) -> str:
    return f"/codex/materials/{tagged(CODEX_CODE_PREFIX, code)}"


async def codex_preview(codes: list[str], filters: Filters) -> PreviewResult:
    narrowed = workspace_filter(filters)
    codexes = select(
        Codex.code,
        Codex.code.label("codex_code"),
        Codex.deleted_at.is_not(None).label("deleted"),
        Codex.title,
        Codex.description,
    ).where(Codex.code.in_(codes))
    async with session_scope() as s:
        rows = {row.code: row for row in await s.execute(codexes)}
        rest = [code for code in codes if code not in rows]
        if rest:
            notes = (
                select(
                    CodexNote.code,
                    CodexNote.codex_code,
                    (CodexNote.deleted_at.is_not(None) | Codex.deleted_at.is_not(None)).label(
                        "deleted"
                    ),
                    CodexNote.title,
                    CodexNote.description,
                )
                .join(Codex, Codex.code == CodexNote.codex_code)
                .where(CodexNote.code.in_(rest))
            )
            rows.update({row.code: row for row in await s.execute(notes)})
        mounted: set[str] | None = None
        if narrowed is not None and rows:
            mounts = select(CodexMount.codex_code).where(
                CodexMount.workspace_code == narrowed,
                CodexMount.enabled.is_(True),
                CodexMount.codex_code.in_({row.codex_code for row in rows.values()}),
            )
            mounted = set((await s.execute(mounts)).scalars())
    result: dict[str, Preview | Miss] = {}
    for code in codes:
        row = rows.get(code)
        if row is None:
            result[code] = Miss.NOT_FOUND
        elif mounted is not None and row.codex_code not in mounted:
            result[code] = Miss.FOREIGN_SCOPE
        elif row.deleted:
            result[code] = Miss.DELETED
        else:
            result[code] = Preview(row.title, row.description, materials_page(row.code))
    return result


__all__ = ["codex_preview", "materials_page"]
