"""Codex MCP tools — the development rules mounted into the active workspace, read and kept.

For the agent the mounted codexes are ONE canvas: their slugs are the first segments of every
path (``python/test/fixtures``), and nothing outside the canvas exists here. Which codexes are
mounted, and whether the agent may write in each, is the person's choice — no tool here mounts,
creates a codex or edits one; the agent writes the notes inside.

A target is a ``CODEX@`` code (a codex or a note — one prefix for both) or a path. The code is
for references that survive moves and renames; the path is for finding your way. The services
hold every rule (``codex/crud``); this file only words them for the agent and names the way out.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.modules.codex.codes import bare_code
from src.modules.codex.constants import CODEX_CODE_PREFIX
from src.modules.codex.crud import mount as mount_crud
from src.modules.codex.crud import note as note_crud
from src.modules.codex.crud import read
from src.modules.codex.rules import agent_may_write
from src.modules.workbench.dto import (
    AgentCodexChild,
    AgentCodexHit,
    AgentCodexIndex,
    AgentCodexNode,
    AgentCodexNoteWritten,
    AgentCodexRow,
    AgentCodexRules,
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
        f"Nothing at the path {target.strip().strip('/')!r} in the codexes mounted into "
        f"{active.title!r} — codex_tree shows what is there."
    )


async def _writable(active: Workspace, node: read.Node) -> bool:
    return agent_may_write(await mount_crud.mount_get(node.codex.code, active.code))


def _tree(branch: read.Branch) -> AgentCodexTreeNode:
    row = branch.node.note or branch.node.codex
    return AgentCodexTreeNode(
        code=branch.node.code,
        slug=row.slug,
        title=row.title,
        children=[_tree(child) for child in branch.children],
    )


def _written(active: Workspace, node: read.Node) -> AgentCodexNoteWritten:
    return AgentCodexNoteWritten(
        workspace=active.code, workspace_title=active.title, code=node.code, path=node.path
    )


def register(mcp: "FastMCP") -> None:

    @mcp.tool()
    async def codex_index() -> AgentCodexIndex:
        """List the codexes mounted into this workspace — the development rules you work by.

        A codex is a set of rules on one theme that does not depend on the project («Python
        backend», «Vue frontend»), with a tree of notes inside. The person mounts codexes into a
        workspace; together they are your canvas, and every path starts with a codex slug.
        `description` says when to turn to a codex; `agent_can_edit` — whether you may write
        notes in it here. Read a codex's rules with codex_rules before working by it.
        """
        active = await require_active()
        return AgentCodexIndex(
            workspace=active.code,
            workspace_title=active.title,
            codexes=[
                AgentCodexRow(
                    code=codex.code,
                    slug=codex.slug,
                    title=codex.title,
                    description=codex.description,
                    agent_can_edit=mount.agent_can_edit,
                )
                for mount, codex in await mount_crud.mount_list(active.code)
            ],
        )

    @mcp.tool()
    async def codex_rules(codex: str) -> AgentCodexRules:
        """Read the rules of working in one codex — how its notes are meant to be read and kept.

        Args:
            codex: The codex — its CODEX@ code or its slug, as codex_index lists it.
        """
        active = await require_active()
        if "/" in codex.strip().strip("/"):
            raise ValueError(
                f"{codex!r} is a path into a codex — codex_rules takes the codex itself: its slug "
                "(the first segment) or its CODEX@ code."
            )
        node = await _node(active, codex)
        if not node.is_codex:
            raise ValueError(
                f"{code_of(node.code)} is a note of the codex {node.codex.slug!r} — the rules are "
                f"codex_rules({node.codex.slug!r}); the note itself is codex_get."
            )
        return AgentCodexRules(
            workspace=active.code,
            workspace_title=active.title,
            code=node.codex.code,
            slug=node.codex.slug,
            title=node.codex.title,
            rules=node.codex.body,
        )

    @mcp.tool()
    async def codex_get(target: str) -> AgentCodexNode:
        """Read one codex or note and see what lies directly under it.

        A note comes whole — its text, path and parent. A codex comes as its title and
        description (its rules: codex_rules). The children come as a list to choose from — code,
        slug, title, description and how many children each has — without their text: open the
        one you need with another codex_get.

        Args:
            target: A CODEX@ code, or a path from the canvas root — `python/test`.
        """
        active = await require_active()
        if read.is_root(target):
            raise ValueError(_ROOT_READ)
        node = await _node(active, target)
        children = await read.children_of(active.code, node.path) or []
        note = node.note
        return AgentCodexNode(
            workspace=active.code,
            workspace_title=active.title,
            code=node.code,
            kind="codex" if node.is_codex else "note",
            path=node.path,
            codex_code=node.codex.code,
            parent_code=None if note is None else (note.parent_code or note.codex_code),
            title=(note or node.codex).title,
            description=(note or node.codex).description,
            body=note.body if note else "",
            writable=await _writable(active, node),
            children=[
                AgentCodexChild(
                    code=child.node.code,
                    slug=child.node.note.slug,
                    title=child.node.note.title,
                    description=child.node.note.description,
                    children=child.child_count,
                )
                for child in children
            ],
        )

    @mcp.tool()
    async def codex_tree(target: str = "") -> AgentCodexTree:
        """Show the tree down from a point — codes, slugs and titles, no descriptions or text.

        From the root (`/` or empty) — every mounted codex. The tree is never cut: the codexes
        are at most four levels deep (codex / note / note / note).

        Args:
            target: A CODEX@ code or a path; `/` or empty for the whole canvas.
        """
        active = await require_active()
        root = "/" if read.is_root(target) else (await _node(active, target)).path
        forest = await read.subtree(active.code, None if root == "/" else root) or []
        return AgentCodexTree(
            workspace=active.code,
            workspace_title=active.title,
            root=root,
            nodes=[_tree(branch) for branch in forest],
        )

    @mcp.tool()
    async def codex_search(query: str, path: str | None = None) -> AgentCodexSearch:
        """Find codexes and notes whose title, description or text holds `query`, any case.

        Each hit carries its code, path, title, description and a fragment around the match.

        Args:
            query: What to look for — a word or a phrase, matched as written, case aside.
            path: Search only this branch — a CODEX@ code or a path; omit for the whole canvas.
        """
        active = await require_active()
        under = None if read.is_root(path) else (await _node(active, path or "")).path
        hits = await read.search(active.code, query, under) or []
        return AgentCodexSearch(
            workspace=active.code,
            workspace_title=active.title,
            hits=[
                AgentCodexHit(
                    code=hit.node.code,
                    path=hit.node.path,
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
        slug: str,
        title: str,
        description: str | None = None,
        body: str | None = None,
    ) -> AgentCodexNoteWritten:
        """Add a note under a codex or a note — where the mount lets you write.

        A note with children is a section: its text is the summary of what lies below
        (`python/test` — the testing standard in brief; its children — the details). The tree
        is at most four levels deep: codex / note / note / note.

        Args:
            parent: The codex or note to add under — a CODEX@ code or a path.
            slug: The note's path segment — a-z, 0-9 and '-', free among its siblings.
            title: What the note is, one line.
            description: When to read it — the line a reader decides by whether to open it.
            body: The text, markdown — skill_get('markdown'); write it now or later with
                content_set(code, "body", …).
        """
        active = await require_active()
        if read.is_root(parent):
            raise ValueError(_ROOT_WRITE)
        node = await _node(active, parent)
        await require_writable_codex(node.codex.code, active)
        row = await note_crud.note_create(
            parent_code=node.code, slug=slug, title=title, description=description, body=body
        )
        return _written(active, await _node(active, code_of(row.code)))

    @mcp.tool()
    async def codex_update(
        target: str,
        title: str | None = None,
        description: str | None = None,
        slug: str | None = None,
        parent: str | None = None,
        after: str | None = None,
    ) -> AgentCodexNoteWritten:
        """Change a note — its fields, its slug, its place. Only what you pass changes.

        Moving is `parent`: the note goes with its whole branch, within its codex, and the tree
        stays within four levels. `after` places it among its siblings. The text is content —
        content_set / content_replace / content_set_section / content_add with the field "body".

        Args:
            target: The note — a CODEX@ code or a path. A codex itself is the person's.
            title: New one-line name.
            description: New "when to read it"; an empty string clears it.
            slug: New path segment — renames the path of everything below it too.
            parent: Move under this codex or note — a CODEX@ code or a path.
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
        new_parent = None if parent is None else (await _node(active, parent)).code
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
            slug=slug,
            parent_code=new_parent,
            after_code=place,
        )
        if row is None:
            raise ValueError(f"{code_of(node.code)} does not exist (or is deleted).")
        return _written(active, await _node(active, code_of(row.code)))


__all__ = ["register"]
