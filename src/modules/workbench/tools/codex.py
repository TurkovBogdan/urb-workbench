"""Codex MCP tools — the development rules mounted into the active workspace, read and kept.

For the agent the mounted codexes are ONE canvas: their segments are the first segments of every
path (``/python/test/fixtures``), and nothing outside the canvas exists here. Which codexes are
mounted, and whether the agent may write in each, is the person's choice — no tool here mounts,
creates a codex or edits one; the agent writes the notes inside.

A target is a ``CODEX@`` code (a codex or a note — one prefix for both) or a path. The code is
for references that survive moves and renames; the path is for finding your way. The services
hold every rule (``codex/crud``); this file only words them for the agent and names the way out.

The agent's way through the canvas is one: ``codex_index`` → the root of each codex the work
touches (``codex_get`` — a codex's ``body`` is its rules of working in its area) → the notes that
bear on the work. Every description here leads along it.

``codex_rules`` is registered apart (``register_rules``) and the server does not call it: the
rules of keeping a codex are meant to grow into fields of their own, and until they do the root's
``body`` is read by ``codex_get`` — a second door to the same text only blurs which one to take.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING

from src.modules.codex.codes import bare_code
from src.modules.codex.constants import CODEX_CODE_PREFIX
from src.modules.codex.crud import mount as mount_crud
from src.modules.codex.crud import note as note_crud
from src.modules.codex.crud import read
from src.modules.workbench.dto import (
    AgentCodexChild,
    AgentCodexHit,
    AgentCodexIndex,
    AgentCodexNode,
    AgentCodexNodeList,
    AgentCodexNoteWritten,
    AgentCodexRow,
    AgentCodexRules,
    AgentCodexRulesList,
    AgentCodexSearch,
    AgentCodexTree,
    AgentCodexTreeNode,
)
from src.modules.workbench.entities.codex import (
    code_of,
    codex_is_the_persons,
    codex_of,
    not_mounted,
    require_writable_codex,
)
from src.modules.workbench.files.rows import codex_note_file_rows
from src.modules.workbench.scope import require_active
from src.modules.workspace.models.workspace import Workspace

if TYPE_CHECKING:  # fastmcp fork — backend only (via mcp_server(ctx))
    from fastmcp import FastMCP

_ROOT_READ = (
    "The canvas root is not a codex or a note — codex_index lists the mounted codexes, "
    "codex_tree('/') shows them all at once."
)
_ROOT_WRITE = (
    "The canvas root holds the codexes themselves, and a codex is created and mounted by the "
    "person. Add your note under a codex or a note — codex_index lists them."
)
# ``after`` — the word that puts a note first among its siblings.
_FIRST = "start"


async def _node(active: Workspace, target: str) -> read.Node:
    """The node a code or path names in the canvas, or a refusal that says why it is not there."""
    node = await read.resolve(active.code, target)
    if node is not None:
        return node
    if "@" in target:
        bare = bare_code(target.strip(), CODEX_CODE_PREFIX) or ""
        if await codex_of(bare) is not None:
            raise ValueError(not_mounted(bare, active))
        raise ValueError(f"{code_of(bare)} does not exist (or is deleted).")
    raise ValueError(
        f"Nothing at the path {_shown(target.strip().strip('/'))!r} in the codexes mounted into "
        f"{active.title!r} — codex_tree shows what is there."
    )


def _shown(path: str) -> str:
    """A canvas path as the agent reads it back — from the root, with a leading slash."""
    return "/" + path


def _segment(node: read.Node) -> str:
    return (node.note or node.codex).segment


async def _rules_target(active: Workspace, item: str) -> read.Node:
    """The codex one item of codex_rules names, or the refusal for that item alone."""
    if read.is_root(item):
        raise ValueError(f"{item!r} is the canvas root, not a codex")
    if "/" in item.strip().strip("/"):
        raise ValueError(
            f"{item!r} is a path into a codex — give the codex itself: its path (the first "
            "segment) or its CODEX@ code"
        )
    node = await _node(active, item)
    if not node.is_codex:
        codex_path = _shown(node.codex.segment)
        raise ValueError(
            f"{code_of(node.code)} is a note of the codex {codex_path!r} — ask for "
            f"{codex_path!r}; the note itself is codex_get"
        )
    return node


async def _get_target(active: Workspace, item: str) -> read.Node:
    """The codex or note one item of codex_get names, or the refusal for that item alone."""
    if read.is_root(item):
        raise ValueError(_ROOT_READ)
    return await _node(active, item)


async def _every(
    active: Workspace,
    items: list[str],
    resolve: Callable[[Workspace, str], Awaitable[read.Node]],
    nothing: str,
) -> list[read.Node]:
    """Every node the items name, in their order, each once — or one refusal naming every item
    at fault: a batch half-answered reads like a batch answered."""
    found: dict[str, read.Node] = {}
    faults: list[str] = []
    for item in items:
        try:
            node = await resolve(active, item)
        except ValueError as fault:
            faults.append(str(fault).rstrip("."))
            continue
        found.setdefault(node.code, node)
    if faults:
        raise ValueError(f"{nothing} — {'; '.join(faults)}. Call again with the list corrected.")
    return list(found.values())


async def _read_node(active: Workspace, node: read.Node) -> AgentCodexNode:
    children = await read.children_of(active.code, node.path) or []
    note = node.note
    row = note or node.codex
    return AgentCodexNode(
        code=node.code,
        path=_shown(node.path),
        segment=row.segment,
        parent_code=None if note is None else (note.parent_code or note.codex_code),
        title=row.title,
        description=row.description,
        body=row.body,
        children=[
            AgentCodexChild(
                code=child.node.code,
                path=_shown(child.node.path),
                segment=_segment(child.node),
                title=child.node.note.title,
                description=child.node.note.description,
                children=child.child_count,
            )
            for child in children
        ],
        files=[] if note is None else await codex_note_file_rows(note.code),
    )


def _tree(branch: read.Branch, *, with_description: bool) -> AgentCodexTreeNode:
    row = branch.node.note or branch.node.codex
    return AgentCodexTreeNode(
        code=branch.node.code,
        path=_shown(branch.node.path),
        segment=row.segment,
        title=row.title,
        description=row.description if with_description else None,
        children=[
            _tree(child, with_description=with_description) for child in branch.children
        ],
    )


def _records(branch: read.Branch) -> int:
    return sum(1 + _records(child) for child in branch.children)


def _written(active: Workspace, node: read.Node) -> AgentCodexNoteWritten:
    return AgentCodexNoteWritten(
        workspace=active.code,
        workspace_title=active.title,
        code=node.code,
        path=_shown(node.path),
        segment=_segment(node),
    )


def register(mcp: "FastMCP") -> None:

    @mcp.tool()
    async def codex_index() -> AgentCodexIndex:
        """List the codexes mounted into this workspace — read it first, before any work.

        A codex is a set of development rules on one theme that does not depend on the project
        («Python backend», «Vue frontend»): its root text holds the rules of working in that
        area, a tree of notes below it the details. The person mounts codexes into a workspace;
        together they are your canvas, and every path starts with a codex (`/python`).

        Each row: `description` — when to turn to the codex, the line to decide by; `records` —
        how many notes it holds at every depth; `editable` — whether you may write notes in it
        here. Next, for each codex the work in front of you touches, open its root with
        codex_get — its `body` is the rules you follow — and codex_tree for its layout.

        An empty list means nothing is mounted here: there are no rules to read, the call did
        not fail.
        """
        active = await require_active()
        records = {
            branch.node.codex.code: _records(branch)
            for branch in await read.subtree(active.code) or []
        }
        return AgentCodexIndex(
            codexes=[
                AgentCodexRow(
                    code=codex.code,
                    path=_shown(codex.segment),
                    segment=codex.segment,
                    title=codex.title,
                    description=codex.description,
                    records=records.get(codex.code, 0),
                    editable=mount.agent_can_edit,
                )
                for mount, codex in await mount_crud.mount_list(active.code)
            ],
        )

    @mcp.tool()
    async def codex_get(targets: list[str]) -> AgentCodexNodeList:
        """Read codexes and notes whole, and see what lies directly under each.

        A codex's `body` is its rules of working in its area: read it before the work the codex
        covers, then go down to the notes that bear on that work. A note's `body` is its text; a
        note with children is a section, and its text sums up what lies below.

        Each node comes with its path and parent (a codex has none) and its children as a list
        to choose from — code, path, segment, title, description and how many children each has
        — without their text. Open the ones the work needs with the next codex_get, all of them
        in one call: the description says whether a child bears on your work, and a body runs up
        to 65 536 characters, so not every child. No `children` key means no children, not a cut
        answer. A note's `files` — FILE@ code, title, description — likewise come only when it
        has some; file_get reads one.

        Always answers with a list, in the order asked, each node once. Either every item is
        found or the call refuses and names every item at fault.

        Args:
            targets: Codexes and notes, mixed as you like — each a CODEX@ code or a path from
                the canvas root (`/python`, `/python/test`).
        """
        active = await require_active()
        if not targets:
            raise ValueError(
                "Name at least one codex or note — a CODEX@ code or a path (`/python/test`)."
            )
        found = await _every(active, targets, _get_target, "Nothing returned")
        return AgentCodexNodeList(nodes=[await _read_node(active, node) for node in found])

    @mcp.tool()
    async def codex_tree(target: str = "", with_description: bool = False) -> AgentCodexTree:
        """Show the tree down from a point — the quick way to find your bearings in the codexes.

        By default the short structure: codes, paths, segments and titles, no text — enough to
        see what a codex holds and where. `with_description=true` adds every node's
        `description`, the «when to read» line, for choosing what to open; the text itself is
        codex_get's. From the root (`/` or empty) — every mounted codex. The tree is never cut: a
        codex is at most four levels deep (codex / note / note / note). A node without
        `children` has none.

        Args:
            target: A CODEX@ code or a path; `/` or empty for the whole canvas.
            with_description: False (default) — the structure only; true — with every node's
                description.
        """
        active = await require_active()
        root = "/" if read.is_root(target) else (await _node(active, target)).path
        forest = await read.subtree(active.code, None if root == "/" else root) or []
        return AgentCodexTree(
            root="/" if root == "/" else _shown(root),
            nodes=[_tree(branch, with_description=with_description) for branch in forest],
        )

    @mcp.tool()
    async def codex_search(query: list[str], within: str | None = None) -> AgentCodexSearch:
        """Find codexes and notes whose title, description or text holds any of the variants —
        when you know the words but not the place.

        A variant is matched as a substring, case aside, with no morphology — so pass the forms
        you expect yourself: `["сессия", "сессию", "сессии", "session"]`. Each record comes once,
        in tree order, with its code, path, segment, title, description and a fragment around
        the earliest variant in the first field that matched. Read a hit whole with codex_get.

        Args:
            query: The variants — words or phrases; a record matches if any of them occurs.
                Blank items are dropped; at least one must remain.
            within: Search only this node's branch — the node itself and everything below it; a
                CODEX@ code or a path. Omit it (or `/`) for the whole canvas.
        """
        active = await require_active()
        if not any(variant.strip() for variant in query):
            raise ValueError(
                "`query` needs at least one non-blank variant — e.g. [\"сессия\", \"сессии\"]."
            )
        under = None if read.is_root(within) else (await _node(active, within or "")).path
        hits = await read.search(active.code, query, under) or []
        return AgentCodexSearch(
            workspace=active.code,
            workspace_title=active.title,
            hits=[
                AgentCodexHit(
                    code=hit.node.code,
                    path=_shown(hit.node.path),
                    segment=_segment(hit.node),
                    title=(hit.node.note or hit.node.codex).title,
                    description=(hit.node.note or hit.node.codex).description,
                    fragment=hit.fragment,
                )
                for hit in hits
            ],
        )

    @mcp.tool()
    async def codex_add(
        parent: str,
        segment: str,
        title: str,
        description: str | None = None,
        body: str | None = None,
    ) -> AgentCodexNoteWritten:
        """Add a note to a codex — a note only: a codex itself is created by the person. Only in
        a codex codex_index shows `editable`.

        Before writing, read the codex's root with codex_get: its rules say what belongs in it
        and where. A note is for what holds beyond the task at hand — a rule, a convention, a
        pitfall worth knowing next time; the course of the work and facts of one project belong
        in the task.

        A note with children is a section: its text sums up what lies below (`/python/test` —
        the testing standard in brief; its children — the details). The tree is at most four
        levels deep: codex / note / note / note. The note goes last among its siblings;
        codex_update `after` moves it.

        The answer carries the note's code and path. Refer to the note by its code: the code
        survives moves and renames, the path does not.

        Args:
            parent: The codex or note to add under — a CODEX@ code or a path (`/python/test`).
            segment: The note's path segment, up to 64 characters — a-z, 0-9, '_' and '-',
                starting with a letter or a digit, free among its siblings.
            title: What the note is — one line, up to 128 characters.
            description: When to read it, up to 512 characters — the line a reader decides by
                whether to open the note; the lists and the tree show it instead of the text.
                Without it the note is found only by search.
            body: The text, markdown — skill_get('markdown'), up to 65 536 characters; write it
                now or later with content_set(code, "body", …).
        """
        active = await require_active()
        if read.is_root(parent):
            raise ValueError(_ROOT_WRITE)
        node = await _node(active, parent)
        await require_writable_codex(node.codex.code, active)
        row = await note_crud.note_create(
            parent_code=node.code,
            segment=segment,
            title=title,
            description=description,
            body=body,
        )
        return _written(active, await _node(active, code_of(row.code)))

    @mcp.tool()
    async def codex_update(
        target: str,
        title: str | None = None,
        description: str | None = None,
        segment: str | None = None,
        parent: str | None = None,
        after: str | None = None,
    ) -> AgentCodexNoteWritten:
        """Change a note — its title, description, segment or place. Only what you pass changes;
        a codex itself is the person's. Only in a codex codex_index shows `editable`.

        The text is not here: it is content — content_set / content_replace /
        content_set_section / content_add with the field "body".

        `segment` renames the note's path and the paths of everything below it; the code stays,
        so a reference by code still holds. `parent` moves the note with its whole branch,
        within its codex, and the tree stays within four levels. `after` places it among its
        siblings — the new ones, when it moves too.

        Args:
            target: The note — a CODEX@ code or a path.
            title: New one-line name, up to 128 characters.
            description: New «when to read it», up to 512 characters; an empty string clears it.
            segment: New path segment, up to 64 characters — a-z, 0-9, '_' and '-', starting
                with a letter or a digit.
            parent: Move under this codex or a note of it — a CODEX@ code or a path.
            after: Place right after this sibling — a CODEX@ code or a path — or "start" to put
                it first.
        """
        active = await require_active()
        if read.is_root(target):
            raise ValueError(_ROOT_WRITE)
        node = await _node(active, target)
        if node.is_codex:
            raise ValueError(codex_is_the_persons(node.code))
        await require_writable_codex(node.codex.code, active)
        new_parent = None
        if parent is not None:
            parent_node = await _node(active, parent)
            # The person may carry a note into another codex; the agent's move stays inside one —
            # the codexes it reads are the person's arrangement, not its to reshuffle.
            if parent_node.codex.code != node.codex.code:
                raise ValueError(
                    f"{code_of(node.code)} belongs to the codex {_shown(node.codex.segment)!r}; a "
                    "note moves only within its codex, not into "
                    f"{_shown(parent_node.codex.segment)!r}."
                )
            new_parent = parent_node.code
        if after is None:
            place: str | None | object = note_crud.KEEP
        elif after.strip() == _FIRST:
            place = None
        else:
            place = (await _node(active, after)).code
        row = await note_crud.note_update(
            node.code,
            title=title,
            description=description,
            segment=segment,
            parent_code=new_parent,
            after_code=place,
        )
        if row is None:
            raise ValueError(f"{code_of(node.code)} does not exist (or is deleted).")
        return _written(active, await _node(active, code_of(row.code)))


def register_rules(mcp: "FastMCP") -> None:
    """``codex_rules`` — kept off the server until the rules of keeping a codex are fields of
    their own (see the module docstring); the tests register it on their own server."""

    @mcp.tool()
    async def codex_rules(codexes: list[str]) -> AgentCodexRulesList:
        """Read how one or several codexes are kept — the rules of writing notes in each.

        A codex's rules say how its notes are written and arranged, its top-level structure
        included. You need them before you change or extend a codex — adding, moving or
        rewriting its notes — not for ordinary work or for reading notes as context.

        Always answers with a list, in the order asked, each codex once. Either every item is a
        mounted codex or the call refuses and names every item at fault.

        Args:
            codexes: The codexes — each a path as codex_index lists it (`/python`) or a CODEX@
                code. A path into a codex or a note's code is refused: give the codex itself.
        """
        active = await require_active()
        if not codexes:
            raise ValueError("Name at least one codex — its path (`/python`) or CODEX@ code.")
        found = await _every(active, codexes, _rules_target, "No rules returned")
        return AgentCodexRulesList(
            nodes=[
                AgentCodexRules(
                    code=node.codex.code,
                    path=_shown(node.codex.segment),
                    segment=node.codex.segment,
                    title=node.codex.title,
                    rules=node.codex.body,
                )
                for node in found
            ]
        )


__all__ = ["register", "register_rules"]
