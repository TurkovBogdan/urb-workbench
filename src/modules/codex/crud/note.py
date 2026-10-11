"""CRUD for ``CodexNote`` — the tree inside a codex, written by the person and by the agent.

Each function owns its session. ``None`` / ``False`` means there is no such live row; a broken
rule is a ``ValueError`` naming the rule and the numbers, raised before anything is written.

**What the service holds that the schema cannot.** The parent is alive and in the same codex; a
move does not put a note under itself; the tree stays within ``DEPTH_MAX`` levels, a moved
subtree counted whole; a slug is free among live siblings (the partial index is the safety net,
this is the refusal that names the sibling). Depth is found by climbing to the root — the tree is
at most four levels, so the climb is at most three reads.

**One writer at a time on the structure.** The person and the agent both move notes, and two
crossing moves, each valid alone, can close a cycle. Every structural change (create, move,
rename, delete, restore) runs inside ``write_scope`` — ``BEGIN IMMEDIATE`` on SQLite already
serialises writers — and on PostgreSQL also takes one transaction-level advisory lock for the
whole codex tree.

**Deleting.** Soft by default. A note with live children is not deleted unless ``with_branch``
says the whole branch goes — the agent surface never passes it and refuses with the list; the
interface asks the person. A branch is deleted under one mark, and a restore brings back exactly
what left with it.

Every write goes through the ORM, so the change feed sees each row it touched.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import func, select, text

from src.core.database import session_scope, write_scope
from src.core.utils.date import utc_now
from src.modules.codex.constants import BODY_MAX, DESCRIPTION_MAX, SORT_DEFAULT, SORT_STEP, TITLE_MAX
from src.modules.codex.crud.code import codex_new_code
from src.modules.codex.models import Codex, CodexNote
from src.modules.codex.rules import TOP_NOTE_DEPTH, depth_problem, slug_problem
from src.modules.codex.text import fit

# ``"codex"`` in ASCII — one key for the whole tree: structure changes are rare and short, and a
# per-codex key would not stop a move across two codexes from racing anyway.
_TREE_LOCK_KEY = 0x636F646578

# ``after_code`` left out: the note keeps its place (or goes to the end of a new row).
KEEP: object = object()


class NoteHasChildren(ValueError):
    """A note with live children was asked to go alone. The surfaces need the children, not only
    the sentence: the interface asks the person what to do with them, the agent is told which to
    delete first.

    ``children`` holds ``(code, slug)`` pairs, not rows: the refusal rolls the session back, and a
    row read after that is detached and expired.
    """

    def __init__(self, code: str, children: list[CodexNote]) -> None:
        self.code = code
        self.children = [(c.code, c.slug) for c in children]
        listed = ", ".join(f"CODEX@{c} ({slug})" for c, slug in self.children)
        super().__init__(
            f"CODEX@{code} has {len(children)} live child note(s): {listed} — delete them "
            "first, or delete the whole branch."
        )


@dataclass(frozen=True)
class _Parent:
    """Where a note hangs: its codex, the parent note (``None`` — the codex's top level), and the
    depth of that parent (the codex is 1)."""

    codex: Codex
    note: CodexNote | None
    depth: int

    @property
    def note_code(self) -> str | None:
        return self.note.code if self.note else None

    @property
    def name(self) -> str:
        return f"note {self.note.slug!r}" if self.note else f"codex {self.codex.slug!r}"


async def _lock_tree(s) -> None:
    if s.bind.dialect.name == "postgresql":
        await s.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": _TREE_LOCK_KEY})


def _slug(value: str) -> str:
    problem = slug_problem(value)
    if problem:
        raise ValueError(f"Note slug refused: {problem}.")
    return value


def _title(value: str) -> str:
    title = fit(value.strip(), TITLE_MAX, "Note title")
    if not title:
        raise ValueError("Note title is empty — a note is found by its title in every list.")
    return title


async def _ancestors(s, note: CodexNote) -> list[CodexNote]:
    """The note's parents up to the codex's top level, nearest first."""
    chain: list[CodexNote] = []
    seen = {note.code}
    current = note
    while current.parent_code is not None and current.parent_code not in seen:
        current = await s.get(CodexNote, current.parent_code)
        if current is None:
            break
        seen.add(current.code)
        chain.append(current)
    return chain


async def _depth(s, note: CodexNote) -> int:
    return TOP_NOTE_DEPTH + len(await _ancestors(s, note))


async def _descendants(s, code: str, *, live_only: bool) -> list[CodexNote]:
    """Every note below ``code``, breadth first; ``seen`` guards against a cycle that reached the
    database past the service."""
    found: list[CodexNote] = []
    seen = {code}
    frontier = [code]
    while frontier:
        stmt = select(CodexNote).where(CodexNote.parent_code.in_(frontier))
        if live_only:
            stmt = stmt.where(CodexNote.deleted_at.is_(None))
        children = [c for c in (await s.scalars(stmt)).all() if c.code not in seen]
        seen.update(c.code for c in children)
        found.extend(children)
        frontier = [c.code for c in children]
    return found


async def _height(s, note: CodexNote, *, live_only: bool = True) -> int:
    """Levels in the branch rooted at ``note``, the note itself counted."""
    height, frontier = 1, [note.code]
    seen = {note.code}
    while True:
        stmt = select(CodexNote.code).where(CodexNote.parent_code.in_(frontier))
        if live_only:
            stmt = stmt.where(CodexNote.deleted_at.is_(None))
        frontier = [c for c in (await s.scalars(stmt)).all() if c not in seen]
        if not frontier:
            return height
        seen.update(frontier)
        height += 1


async def _parent(s, code: str) -> _Parent:
    """Resolve a parent given by code — a codex (its top level) or a note. Both must be alive."""
    codex = await s.get(Codex, code)
    if codex is not None:
        if codex.deleted_at is not None:
            raise ValueError(f"CODEX@{code} is a deleted codex — nothing can be added to it.")
        return _Parent(codex=codex, note=None, depth=1)
    note = await s.get(CodexNote, code)
    if note is None or note.deleted_at is not None:
        raise ValueError(f"CODEX@{code} is neither a live codex nor a live note of one.")
    codex = await s.get(Codex, note.codex_code)
    if codex is None or codex.deleted_at is not None:
        raise ValueError(f"CODEX@{code} belongs to a deleted codex.")
    return _Parent(codex=codex, note=note, depth=await _depth(s, note))


def _siblings(stmt, codex_code: str, parent_code: str | None):
    stmt = stmt.where(CodexNote.codex_code == codex_code)
    if parent_code is None:
        return stmt.where(CodexNote.parent_code.is_(None))
    return stmt.where(CodexNote.parent_code == parent_code)


async def _require_slug_free(
    s, parent: _Parent, slug: str, *, own_code: str | None = None
) -> None:
    holder = await s.scalar(
        _siblings(select(CodexNote), parent.codex.code, parent.note_code).where(
            CodexNote.slug == slug, CodexNote.deleted_at.is_(None)
        )
    )
    if holder is not None and holder.code != own_code:
        raise ValueError(
            f"The slug {slug!r} is taken under the {parent.name} by the note {holder.title!r} "
            f"(CODEX@{holder.code}) — a path must lead to one note. Pick another slug."
        )


async def _bottom_sort(s, codex_code: str, parent_code: str | None) -> int:
    lowest = await s.scalar(
        _siblings(select(func.min(CodexNote.sort)), codex_code, parent_code).where(
            CodexNote.deleted_at.is_(None)
        )
    )
    return SORT_DEFAULT if lowest is None else lowest - SORT_STEP


async def _place_after(s, note: CodexNote, after_code: str | None) -> None:
    """Put ``note`` right after ``after_code`` among its live siblings (``None`` — first) and
    renumber the row, as ``tasks`` does: an even row never runs out of gaps."""
    await s.flush()
    row = list(
        (
            await s.scalars(
                _siblings(select(CodexNote), note.codex_code, note.parent_code)
                .where(CodexNote.deleted_at.is_(None))
                .order_by(CodexNote.sort.desc(), CodexNote.code.asc())
            )
        ).all()
    )
    if after_code is not None and all(item.code != after_code for item in row):
        raise ValueError(
            f"CODEX@{after_code} is not a sibling of CODEX@{note.code} — a note is placed only "
            "among the notes of its own parent."
        )
    order = [item for item in row if item.code != note.code]
    at = 0 if after_code is None else next(i for i, x in enumerate(order) if x.code == after_code) + 1
    order.insert(at, note)
    top = len(order) * SORT_STEP
    for index, item in enumerate(order):
        item.sort = top - index * SORT_STEP


async def note_create(
    *,
    parent_code: str,
    slug: str,
    title: str,
    description: str | None = None,
    body: str | None = None,
) -> CodexNote:
    """A new note under a codex (its top level) or under a note, at the end of that row."""
    values = {
        "slug": _slug(slug),
        "title": _title(title),
        "description": fit(description, DESCRIPTION_MAX, "Note description"),
        "body": fit(body, BODY_MAX, "Note body"),
    }
    async with write_scope() as s:
        await _lock_tree(s)
        parent = await _parent(s, parent_code)
        problem = depth_problem(parent.depth)
        if problem:
            raise ValueError(f"A note cannot go under the {parent.name}: {problem}.")
        await _require_slug_free(s, parent, values["slug"])
        row = CodexNote(
            code=await codex_new_code(s),
            codex_code=parent.codex.code,
            parent_code=parent.note_code,
            sort=await _bottom_sort(s, parent.codex.code, parent.note_code),
            **values,
        )
        s.add(row)
        await s.flush()
        await s.refresh(row)
    return row


async def note_get(code: str, *, include_deleted: bool = False) -> CodexNote | None:
    stmt = select(CodexNote).where(CodexNote.code == code)
    if not include_deleted:
        stmt = stmt.where(CodexNote.deleted_at.is_(None))
    async with session_scope() as s:
        return await s.scalar(stmt)


async def note_update(
    code: str,
    *,
    title: str | None = None,
    description: str | None = None,
    body: str | None = None,
    slug: str | None = None,
    parent_code: str | None = None,
    after_code: str | None | object = KEEP,
) -> CodexNote | None:
    """Edit fields, rename, move and place — one call, all checked before anything is written.

    ``parent_code`` — move under that codex (its top level) or note, in the same codex only;
    ``after_code`` — place right after that sibling, ``None`` — first in the row; left out, a
    moved note goes to the end of its new row and an unmoved one stays put. ``None`` in the
    result — no such live note.
    """
    values: dict[str, str] = {}
    if title is not None:
        values["title"] = _title(title)
    if description is not None:
        values["description"] = fit(description, DESCRIPTION_MAX, "Note description")
    if body is not None:
        values["body"] = fit(body, BODY_MAX, "Note body")
    if slug is not None:
        values["slug"] = _slug(slug)
    structural = "slug" in values or parent_code is not None or after_code is not KEEP

    async with write_scope() as s:
        if structural:
            await _lock_tree(s)
        row = await s.get(CodexNote, code)
        if row is None or row.deleted_at is not None:
            return None
        current = await _parent(s, row.parent_code or row.codex_code)
        target = current

        if parent_code is not None:
            target = await _parent(s, parent_code)
            if target.codex.code != row.codex_code:
                raise ValueError(
                    f"CODEX@{code} belongs to the codex {current.codex.slug!r}; a note moves "
                    f"only within its codex, not into {target.codex.slug!r}."
                )
            if target.note is not None and (
                target.note.code == code
                or code in {a.code for a in await _ancestors(s, target.note)}
            ):
                raise ValueError(
                    f"CODEX@{code} cannot move under the {target.name}: that note is inside its "
                    "own branch, and the move would close a loop."
                )
            problem = depth_problem(target.depth, await _height(s, row))
            if problem:
                raise ValueError(f"CODEX@{code} cannot move under the {target.name}: {problem}.")

        moved = target.note_code != row.parent_code
        if moved or "slug" in values:
            await _require_slug_free(s, target, values.get("slug", row.slug), own_code=code)

        for field, value in values.items():
            setattr(row, field, value)
        if moved:
            row.parent_code = target.note_code
            if after_code is KEEP:
                row.sort = await _bottom_sort(s, row.codex_code, row.parent_code)
        if after_code is not KEEP:
            await _place_after(s, row, after_code)
        await s.flush()
        await s.refresh(row)
    return row


async def _branch_stamp(s, branch: list[str]) -> datetime:
    """A deletion mark nothing in the branch carries yet — one second of precision would otherwise
    let an earlier, separate deletion come back with this branch's restore (``tasks`` does the
    same)."""
    taken = set(
        (
            await s.scalars(
                select(CodexNote.deleted_at).where(
                    CodexNote.code.in_(branch), CodexNote.deleted_at.is_not(None)
                )
            )
        ).all()
    )
    stamp = utc_now()
    while stamp in taken:
        stamp += timedelta(seconds=1)
    return stamp


async def note_delete(code: str, *, with_branch: bool = False, hard: bool = False) -> bool:
    """Delete a note — softly by default. ``True`` — it existed.

    Live children refuse the delete unless ``with_branch``; then the whole branch goes under one
    mark (soft) or physically (hard).
    """
    async with write_scope() as s:
        await _lock_tree(s)
        row = await s.get(CodexNote, code)
        if row is None:
            return False
        live_below = await _descendants(s, code, live_only=True)
        if live_below and not with_branch:
            raise NoteHasChildren(code, [c for c in live_below if c.parent_code == code])
        if hard:
            # Leaves first: the FK cascade would otherwise remove a child the session still
            # means to delete, and the change feed would never hear of it.
            for below in reversed(await _descendants(s, code, live_only=False)):
                await s.delete(below)
                await s.flush()
            await s.delete(row)
            return True
        if row.deleted_at is None:
            # The mark is checked against the whole branch, the already deleted included: those
            # are exactly the rows whose own mark it must not repeat.
            whole = [code, *(n.code for n in await _descendants(s, code, live_only=False))]
            stamp = await _branch_stamp(s, whole)
            for note in (row, *live_below):
                note.deleted_at = stamp
    return True


async def note_restore(code: str) -> bool:
    """Bring a deleted note back with what left with it. ``True`` — it was deleted and is back.

    Refused while the parent or the codex is deleted (restore that first), while a live sibling
    holds the slug, or when the branch would no longer fit the depth limit.
    """
    async with write_scope() as s:
        await _lock_tree(s)
        row = await s.get(CodexNote, code)
        if row is None or row.deleted_at is None:
            return False
        if row.parent_code is not None:
            parent_row = await s.get(CodexNote, row.parent_code)
            if parent_row is None or parent_row.deleted_at is not None:
                raise ValueError(
                    f"CODEX@{code} sits under a deleted note (CODEX@{row.parent_code}) — "
                    "restore that one first."
                )
        parent = await _parent(s, row.parent_code or row.codex_code)
        await _require_slug_free(s, parent, row.slug, own_code=code)

        stamp = row.deleted_at
        branch = [row] + [
            n for n in await _descendants(s, code, live_only=False) if n.deleted_at == stamp
        ]
        height = _restored_height(row, branch)
        problem = depth_problem(parent.depth, height)
        if problem:
            raise ValueError(f"CODEX@{code} cannot come back under the {parent.name}: {problem}.")
        for note in branch:
            note.deleted_at = None
    return True


def _restored_height(root: CodexNote, branch: list[CodexNote]) -> int:
    """Levels of the branch a restore brings back, the root counted."""
    by_parent: dict[str | None, list[CodexNote]] = {}
    for note in branch:
        by_parent.setdefault(note.parent_code, []).append(note)
    height, frontier = 1, [root.code]
    while True:
        frontier = [c.code for code in frontier for c in by_parent.get(code, [])]
        if not frontier:
            return height
        height += 1


__all__ = [
    "KEEP",
    "NoteHasChildren",
    "note_create",
    "note_delete",
    "note_get",
    "note_restore",
    "note_update",
]
