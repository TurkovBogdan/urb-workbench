"""Reads for moving a codex between installations — whole rows, deleted ones included.

A code in the bin is still a taken code, and one code space covers two tables: a codex and a
record. Writes are not here — the import writes its rows in one transaction of its own
(``transfer/apply.py``).
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from sqlalchemy import select

from src.core.database import session_scope
from src.modules.codex.models import Codex, CodexFile, CodexMount, CodexNote


def _codes(codes: Iterable[str]) -> list[str]:
    return sorted(set(codes))


async def rows_by_codes(model: Any, codes: Iterable[str]) -> dict[str, Any]:
    wanted = _codes(codes)
    if not wanted:
        return {}
    async with session_scope() as s:
        rows = (await s.execute(select(model).where(model.code.in_(wanted)))).scalars().all()
    return {row.code: row for row in rows}


async def notes_of(codex_code: str) -> list[CodexNote]:
    """Every record of the codex, deleted ones too, parents before children, each row in order."""
    async with session_scope() as s:
        rows = (await s.execute(select(CodexNote).where(CodexNote.codex_code == codex_code))).scalars().all()
    children: dict[str | None, list[CodexNote]] = {}
    for row in rows:
        children.setdefault(row.parent_code, []).append(row)
    for row_list in children.values():
        row_list.sort(key=lambda row: (-row.sort, row.created_at, row.code))
    ordered: list[CodexNote] = []
    level = children.get(None, [])
    while level:
        ordered.extend(level)
        level = [child for row in level for child in children.get(row.code, [])]
    return ordered


async def bindings_of(note_codes: Iterable[str]) -> dict[tuple[str, str], CodexFile]:
    wanted = _codes(note_codes)
    if not wanted:
        return {}
    async with session_scope() as s:
        rows = (await s.execute(select(CodexFile).where(CodexFile.note_code.in_(wanted)))).scalars().all()
    return {(row.note_code, row.file_code): row for row in rows}


async def code_holders(codes: Iterable[str]) -> tuple[dict[str, Codex], dict[str, CodexNote]]:
    """Which of the codes a codex holds and which a record holds — one code space, two tables."""
    return await rows_by_codes(Codex, codes), await rows_by_codes(CodexNote, codes)


async def live_codex_segments() -> dict[str, str]:
    """``segment → code`` of every live codex."""
    async with session_scope() as s:
        rows = (await s.execute(select(Codex).where(Codex.deleted_at.is_(None)))).scalars().all()
    return {row.segment: row.code for row in rows}


async def mount_of(codex_code: str, workspace_code: str) -> CodexMount | None:
    async with session_scope() as s:
        return await s.get(CodexMount, (codex_code, workspace_code))


__all__ = ["bindings_of", "code_holders", "live_codex_segments", "mount_of", "notes_of", "rows_by_codes"]
