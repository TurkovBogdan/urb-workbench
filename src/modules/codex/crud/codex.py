"""CRUD for ``Codex`` — the person's side: only the interface creates and edits a codex.

Each function owns its session. Reads hide soft-deleted rows unless ``include_deleted`` is passed.
``None`` / ``False`` means there is no such row; a broken rule is a ``ValueError`` that names the
rule and the numbers, raised before anything is written.

A soft-deleted codex keeps its notes and mounts as they were: it simply disappears from every
canvas, and a restore brings it back where it stood. Its segment is freed meanwhile — so a restore
is refused while another live codex holds it.
"""

from __future__ import annotations

from sqlalchemy import select

from src.core.database import session_scope, write_scope
from src.core.utils.date import utc_now
from src.modules.codex.constants import (
    BODY_MAX,
    COLOR_MAX,
    DESCRIPTION_MAX,
    ICON_MAX,
    TITLE_MAX,
)
from src.modules.codex.crud.code import codex_new_code
from src.modules.codex.models import Codex
from src.modules.codex.rules import segment_problem
from src.modules.codex.text import fit


def _segment(value: str) -> str:
    problem = segment_problem(value)
    if problem:
        raise ValueError(f"Codex segment refused: {problem}.")
    return value


def _title(value: str) -> str:
    title = fit(value.strip(), TITLE_MAX, "Codex title")
    if not title:
        raise ValueError("Codex title is empty — a codex is found by its title in every list.")
    return title


async def _require_segment_free(s, segment: str, *, own_code: str | None = None) -> None:
    holder = await s.scalar(
        select(Codex).where(Codex.segment == segment, Codex.deleted_at.is_(None))
    )
    if holder is not None and holder.code != own_code:
        raise ValueError(
            f"Codex segment {segment!r} is taken by the codex {holder.title!r} "
            f"(CODEX@{holder.code}) — two codexes with one segment could not be mounted side by "
            "side. Pick another segment."
        )


async def codex_create(
    *,
    segment: str,
    title: str,
    description: str | None = None,
    body: str | None = None,
    color: str | None = None,
    icon: str | None = None,
) -> Codex:
    """A new codex, mounted nowhere yet."""
    values = {
        "segment": _segment(segment),
        "title": _title(title),
        "description": fit(description, DESCRIPTION_MAX, "Codex description"),
        "body": fit(body, BODY_MAX, "Codex rules"),
        "color": fit(color, COLOR_MAX, "Codex color"),
        "icon": fit(icon, ICON_MAX, "Codex icon"),
    }
    async with write_scope() as s:
        await _require_segment_free(s, values["segment"])
        row = Codex(code=await codex_new_code(s), **values)
        s.add(row)
        await s.flush()
        await s.refresh(row)
    return row


async def codex_get(code: str, *, include_deleted: bool = False) -> Codex | None:
    stmt = select(Codex).where(Codex.code == code)
    if not include_deleted:
        stmt = stmt.where(Codex.deleted_at.is_(None))
    async with session_scope() as s:
        return await s.scalar(stmt)


async def codex_get_by_segment(segment: str) -> Codex | None:
    """The live codex with this segment — the first segment of a path."""
    async with session_scope() as s:
        return await s.scalar(
            select(Codex).where(Codex.segment == segment, Codex.deleted_at.is_(None))
        )


async def codex_list(*, include_deleted: bool = False) -> list[Codex]:
    """Every codex, in the person's order (higher ``sort`` first)."""
    stmt = select(Codex).order_by(Codex.sort.desc(), Codex.code.asc())
    if not include_deleted:
        stmt = stmt.where(Codex.deleted_at.is_(None))
    async with session_scope() as s:
        return list((await s.scalars(stmt)).all())


async def codex_update(
    code: str,
    *,
    segment: str | None = None,
    title: str | None = None,
    description: str | None = None,
    body: str | None = None,
    color: str | None = None,
    icon: str | None = None,
) -> Codex | None:
    """Update the given fields (``None`` = leave alone). ``None`` — no such live codex.

    A new segment renames the first segment of every path inside the codex at once: paths are not
    stored, codes do not change, and every reference by code keeps working.
    """
    values: dict[str, str] = {}
    if segment is not None:
        values["segment"] = _segment(segment)
    if title is not None:
        values["title"] = _title(title)
    if description is not None:
        values["description"] = fit(description, DESCRIPTION_MAX, "Codex description")
    if body is not None:
        values["body"] = fit(body, BODY_MAX, "Codex rules")
    if color is not None:
        values["color"] = fit(color, COLOR_MAX, "Codex color")
    if icon is not None:
        values["icon"] = fit(icon, ICON_MAX, "Codex icon")
    async with write_scope() as s:
        row = await s.get(Codex, code)
        if row is None or row.deleted_at is not None:
            return None
        if "segment" in values:
            await _require_segment_free(s, values["segment"], own_code=code)
        for field, value in values.items():
            setattr(row, field, value)
        await s.flush()
        await s.refresh(row)
    return row


async def codex_delete(code: str, *, hard: bool = False) -> bool:
    """Delete a codex: softly (the default) or with its notes and mounts. ``True`` — it existed."""
    async with write_scope() as s:
        row = await s.get(Codex, code)
        if row is None:
            return False
        if hard:
            await s.delete(row)
        elif row.deleted_at is None:
            row.deleted_at = utc_now()
    return True


async def codex_restore(code: str) -> bool:
    """Bring a deleted codex back. ``True`` — it is back; a taken segment refuses the restore."""
    async with write_scope() as s:
        row = await s.get(Codex, code)
        if row is None or row.deleted_at is None:
            return False
        await _require_segment_free(s, row.segment)
        row.deleted_at = None
    return True


__all__ = [
    "codex_create",
    "codex_delete",
    "codex_get",
    "codex_get_by_segment",
    "codex_list",
    "codex_restore",
    "codex_update",
]
