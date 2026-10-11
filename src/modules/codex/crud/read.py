"""Reading a workspace's canvas: paths, a node by code or path, children, a subtree, search.

Everything here is seen **from a workspace**: the canvas is the live codexes mounted into it, and
a codex that is not mounted there is not found — by code, by path or by search — exactly as a
code of another workspace is not found elsewhere in the app.

The canvas is read whole into memory per call (``_Canvas``): codexes are mounted by the handful and
hold notes by the hundred, so one query per table beats a query per level, and paths, depth and
child counts then come from dictionaries. Case is folded in Python (``casefold``), never in SQL:
SQLite's ``lower()`` folds ASCII only, so a Cyrillic query would match on PostgreSQL and miss on
SQLite.

A target is either a code (``CODEX@…`` — the prefix is required, since a ten-character slug of hex
letters would read as a bare code) or a path from the canvas root: ``python/test``, slashes at the
ends ignored. ``""`` and ``"/"`` are the root itself, which is not a node.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from sqlalchemy import select

from src.core.database import session_scope
from src.modules.codex.codes import bare_code
from src.modules.codex.constants import CODEX_CODE_PREFIX
from src.modules.codex.models import Codex, CodexMount, CodexNote

_FRAGMENT_RADIUS = 60


@dataclass(frozen=True)
class Node:
    """A codex or a note, as the canvas sees it. ``note`` is ``None`` for a codex."""

    codex: Codex
    note: CodexNote | None
    path: str
    depth: int

    @property
    def code(self) -> str:
        return self.note.code if self.note else self.codex.code

    @property
    def is_codex(self) -> bool:
        return self.note is None


@dataclass(frozen=True)
class Child:
    node: Node
    child_count: int


@dataclass
class Branch:
    """A node and everything below it, for a tree view."""

    node: Node
    children: list[Branch] = field(default_factory=list)


@dataclass(frozen=True)
class Hit:
    node: Node
    fragment: str


def is_root(target: str | None) -> bool:
    return not (target or "").strip().strip("/")


class _Canvas:
    """The live codexes mounted into one workspace, and their live notes."""

    def __init__(self, codexes: list[Codex], notes: list[CodexNote]) -> None:
        self.codexes = codexes
        self.codex_by_code = {c.code: c for c in codexes}
        self.codex_by_slug = {c.slug: c for c in codexes}
        self.note_by_code = {n.code: n for n in notes}
        self.children: dict[tuple[str, str | None], list[CodexNote]] = defaultdict(list)
        for note in sorted(notes, key=lambda n: (-n.sort, n.code)):
            self.children[(note.codex_code, note.parent_code)].append(note)

    def node_of_codex(self, codex: Codex) -> Node:
        return Node(codex=codex, note=None, path=codex.slug, depth=1)

    def node_of_note(self, note: CodexNote) -> Node:
        slugs = [note.slug]
        current = note
        while current.parent_code is not None:
            current = self.note_by_code[current.parent_code]
            slugs.append(current.slug)
        codex = self.codex_by_code[note.codex_code]
        return Node(
            codex=codex,
            note=note,
            path="/".join([codex.slug, *reversed(slugs)]),
            depth=len(slugs) + 1,
        )

    def kids(self, node: Node) -> list[CodexNote]:
        return self.children[(node.codex.code, node.note.code if node.note else None)]

    def by_code(self, code: str) -> Node | None:
        if code in self.codex_by_code:
            return self.node_of_codex(self.codex_by_code[code])
        note = self.note_by_code.get(code)
        return self.node_of_note(note) if note else None

    def by_path(self, path: str) -> Node | None:
        head, *rest = path.strip("/").split("/")
        codex = self.codex_by_slug.get(head)
        if codex is None:
            return None
        node = self.node_of_codex(codex)
        for slug in rest:
            match = next((n for n in self.kids(node) if n.slug == slug), None)
            if match is None:
                return None
            node = self.node_of_note(match)
        return node

    def resolve(self, target: str) -> Node | None:
        target = target.strip()
        if "@" in target:
            return self.by_code(bare_code(target, CODEX_CODE_PREFIX))
        return self.by_path(target)

    def branch(self, node: Node) -> Branch:
        return Branch(
            node=node, children=[self.branch(self.node_of_note(n)) for n in self.kids(node)]
        )


async def _canvas(workspace_code: str) -> _Canvas:
    """The canvas of a workspace: its live mounted codexes in the person's order."""
    return await _load(
        select(Codex)
        .join(CodexMount, CodexMount.codex_code == Codex.code)
        .where(CodexMount.workspace_code == workspace_code, Codex.deleted_at.is_(None))
        .order_by(CodexMount.sort.desc(), Codex.code.asc())
    )


async def _load(codexes_stmt) -> _Canvas:
    """One read: the codexes the statement selects and their live notes — two queries, whatever
    the tree's size.

    A note whose ancestor is deleted is cut off with it — a soft delete of a branch marks every
    row, but an ancestor deleted alone (its children moved away first) must not leave an orphan
    path behind, so the walk keeps only notes whose parents are all in the set.
    """
    async with session_scope() as s:
        codexes = list((await s.scalars(codexes_stmt)).all())
        notes = (
            list(
                (
                    await s.scalars(
                        select(CodexNote).where(
                            CodexNote.codex_code.in_([c.code for c in codexes]),
                            CodexNote.deleted_at.is_(None),
                        )
                    )
                ).all()
            )
            if codexes
            else []
        )
    live = {n.code: n for n in notes}

    def reachable(note: CodexNote) -> bool:
        seen = set()
        while note.parent_code is not None:
            if note.parent_code in seen or note.parent_code not in live:
                return False
            seen.add(note.parent_code)
            note = live[note.parent_code]
        return True

    return _Canvas(codexes, [n for n in notes if reachable(n)])


async def codex_branch(codex_code: str) -> Branch | None:
    """A live codex and its whole tree, mounted or not — the person's view of one codex."""
    canvas = await _load(
        select(Codex).where(Codex.code == codex_code, Codex.deleted_at.is_(None))
    )
    if not canvas.codexes:
        return None
    return canvas.branch(canvas.node_of_codex(canvas.codexes[0]))


async def note_node(code: str) -> Node | None:
    """A live note with its path, wherever it is mounted; ``None`` — no such live note, or it is
    cut off under a deleted ancestor or codex."""
    async with session_scope() as s:
        codex_code = await s.scalar(
            select(CodexNote.codex_code).where(CodexNote.code == code)
        )
    if codex_code is None:
        return None
    canvas = await _load(
        select(Codex).where(Codex.code == codex_code, Codex.deleted_at.is_(None))
    )
    note = canvas.note_by_code.get(code)
    return canvas.node_of_note(note) if note else None


async def resolve(workspace_code: str, target: str) -> Node | None:
    """The codex or note ``target`` names in this workspace's canvas; ``None`` — not there.

    The root is not a node: ``ValueError`` — the surfaces point at the index instead. A code of a
    foreign type is a ``ValueError`` too (``codes.bare_code``).
    """
    if is_root(target):
        raise ValueError("The canvas root is not a codex or a note — list the codexes instead.")
    return (await _canvas(workspace_code)).resolve(target)


async def children_of(workspace_code: str, target: str) -> list[Child] | None:
    """The live children of a codex or a note, each with the number of its own live children.

    ``None`` — the target is not in the canvas.
    """
    canvas = await _canvas(workspace_code)
    node = canvas.resolve(target) if not is_root(target) else None
    if node is None:
        return None
    return [
        Child(node=canvas.node_of_note(n), child_count=len(canvas.kids(canvas.node_of_note(n))))
        for n in canvas.kids(node)
    ]


async def subtree(workspace_code: str, target: str | None = None) -> list[Branch] | None:
    """The tree below ``target`` whole — the depth limit keeps it small; from the root, every
    codex of the canvas. ``None`` — the target is not in the canvas."""
    canvas = await _canvas(workspace_code)
    if is_root(target):
        return [canvas.branch(canvas.node_of_codex(c)) for c in canvas.codexes]
    node = canvas.resolve(target)
    return None if node is None else [canvas.branch(node)]


def _fragment(text: str, needle: str) -> str:
    at = text.casefold().find(needle)
    if at < 0:
        return ""
    start = max(0, at - _FRAGMENT_RADIUS)
    end = min(len(text), at + len(needle) + _FRAGMENT_RADIUS)
    return ("…" if start else "") + text[start:end] + ("…" if end < len(text) else "")


async def search(workspace_code: str, query: str, under: str | None = None) -> list[Hit] | None:
    """Codexes and notes of the canvas whose title, description or text holds ``query`` in any
    case; within ``under``'s branch when given (``None`` — that branch is not in the canvas).

    The fragment comes from the first field that matched, in the order title, description, text.
    """
    needle = query.strip().casefold()
    if not needle:
        raise ValueError("The search query is empty.")
    canvas = await _canvas(workspace_code)
    if is_root(under):
        roots = [canvas.node_of_codex(c) for c in canvas.codexes]
    else:
        start = canvas.resolve(under)
        if start is None:
            return None
        roots = [start]

    hits: list[Hit] = []
    stack = [canvas.branch(root) for root in reversed(roots)]
    while stack:
        branch = stack.pop()
        row = branch.node.note or branch.node.codex
        for value in (row.title, row.description, row.body):
            if value and needle in value.casefold():
                hits.append(Hit(node=branch.node, fragment=_fragment(value, needle)))
                break
        stack.extend(reversed(branch.children))
    return hits


__all__ = [
    "Branch",
    "Child",
    "Hit",
    "Node",
    "children_of",
    "codex_branch",
    "is_root",
    "note_node",
    "resolve",
    "search",
    "subtree",
]
