"""Layout MCP tools: the active workspace's groups and what is filed in them.

**The person decides the layout, the agent writes it down.** Group editing is handed over here
not because the topic stopped being the person's business, but because without it the agent
cannot carry out a request said out loud: "make a theme for billing and move these three there".
The danger has not gone away, it has moved: it used to be held back by the missing tool, now it
is held back by the descriptions — they say to create a group on request, not because the
backlog looked untidy to the agent.

Four tools for three scenarios: view the layout, edit it, file work into it. ``tasks_regroup``
lives here rather than among the task tools because of what it returns: it changes the layout,
not a card, and replies with the layout.

There is still no single-group read — ``groups_list`` carries exactly the same fields, and a
``group_get`` would differ from it only by returning one row instead of three.

**Styling (colour, icon) is not among the arguments.** ``AgentGroupRow`` deliberately does not
carry it: it tells the agent nothing and would cost two fields in every reply row. Let the agent
write them and you get the only blind field on the surface — one it can neither read back nor
verify: there is no palette in the backend at all, it lives in the frontend. The person chooses
how a group looks.

A position is given by a neighbour (``place_after`` / ``place_before``), not by a ``sort``
number: the number is the list's internal mechanics, and the agent has no way to hit it.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.modules.tasks.codes import bare_code, tagged
from src.modules.tasks.constants import GROUP_CODE_PREFIX, TASK_CODE_PREFIX
from src.modules.tasks.crud import group as group_crud
from src.modules.tasks.crud import task as task_crud
from src.modules.tasks.dto import AgentGroupList, AgentGroupRow, AgentTasksRegrouped
from src.modules.tasks.mcp.scope import require_active, require_scope
from src.modules.workspace.models.workspace import Workspace

if TYPE_CHECKING:  # fastmcp fork — backend only (via mcp_server(ctx))
    from fastmcp import FastMCP

# Batch cap for ``tasks_regroup``. It lives here rather than as an argument: a read shows its
# limit through the ``shown``/``total`` numbers, a write has no such device — the limit has to be
# stated as a refusal. The number follows the same reasoning as ``LIST_CAP``: a bigger batch is
# no longer "file these", it is rebuilding the layout, and the person does that on their screen.
REGROUP_CAP = 50


def _group_code(value: str) -> str:
    return bare_code(value, GROUP_CODE_PREFIX) or ""


async def _layout(active: Workspace) -> AgentGroupList:
    """The workspace layout with counters — the shared reply of every tool in this file."""
    rows = await group_crud.group_list_by_workspace(active.code)
    counted = await task_crud.task_count_by_group_codes([row.code for row in rows])
    return AgentGroupList(
        workspace=active.code,
        workspace_title=active.title,
        groups=[
            AgentGroupRow(
                code=row.code,
                title=row.title,
                description=row.description,
                task_count=counted.get(row.code, 0),
            )
            for row in rows
        ],
    )


def _require_title(title: str) -> str:
    stripped = title.strip()
    if not stripped:
        raise ValueError("A group needs a title — a theme with no name cannot be filed under.")
    return stripped


async def _require_free_title(active: Workspace, title: str, *, own: str = "") -> None:
    """Refuse if the title is already taken by a live group of the workspace (case-insensitive).

    The schema has no unique index on the "workspace + title" pair, and without this check one
    layout ends up with both "Billing" and "billing" — the same pitfall that got the free-form
    bucket name removed from the task link.
    """
    taken = await group_crud.group_find_by_title(active.code, title)
    if taken is not None and taken.code != own:
        raise ValueError(
            f"{tagged(GROUP_CODE_PREFIX, taken.code)} is already called {taken.title!r} in "
            f"{active.title!r}. File the work there instead of making a second one, or pick a "
            "name that says how this theme differs."
        )


async def _anchor(after: str | None, before: str | None, *, moving: str = "") -> str | None:
    """The position's reference point, verified BEFORE the first write; ``None`` — no place given.

    The check lives here rather than inside ``group_reorder`` for one reason: reordering is the
    tool's SECOND action, after creating or editing the card. A refusal there would leave behind
    an applied half while the agent is told "it failed": it reads the refusal as "nothing
    happened" and creates the group again. That is exactly the failure mode the whole surface is
    built against, so everything reordering could refuse on is settled before the write.

    ``group_reorder`` keeps its own checks all the same: CRUD is called outside this tool too.
    """
    if after is None and before is None:
        return None
    if after is not None and before is not None:
        raise ValueError(
            "Pass exactly one of place_after / place_before — a position needs one point of "
            "reference, not two."
        )
    anchor = _group_code(after or before or "")
    await require_scope(GROUP_CODE_PREFIX, anchor)
    if await group_crud.group_get(anchor) is None:
        raise ValueError(
            f"{tagged(GROUP_CODE_PREFIX, anchor)} is not a live group here — groups_list says "
            "what the layout is and what may be placed against."
        )
    if moving and anchor == moving:
        raise ValueError(
            f"{tagged(GROUP_CODE_PREFIX, anchor)} cannot be placed relative to itself — name "
            "another group, or leave the position alone."
        )
    return anchor


async def _place(code: str, anchor: str | None, after: str | None) -> None:
    """Move the group next to an already verified reference point."""
    if anchor is None:
        return
    await group_crud.group_reorder(
        code,
        after=anchor if after is not None else None,
        before=None if after is not None else anchor,
    )


def register(mcp: "FastMCP") -> None:

    @mcp.tool()
    async def groups_list() -> AgentGroupList:
        """List the groups of the workspace this session works in.

        A group is a standing theme inside a workspace — billing, interface, infrastructure —
        and a task may sit in one or in none. Read the descriptions before filing a task: they
        say where the boundary of each group runs, which the titles alone do not.

        Takes no workspace: the session is already bound to one. If it is not, this call tells
        you so and names how to fix it.
        """
        return await _layout(await require_active())

    @mcp.tool()
    async def group_create(
        title: str,
        description: str,
        place_after: str | None = None,
        place_before: str | None = None,
    ) -> AgentGroupList:
        """Create a group in the workspace this session works in — a standing theme.

        The layout belongs to the person: make a group when they ask for one, not because the
        backlog looks untidy to you. Three themes they recognise beat seven you invented, and a
        task filed under a theme nobody uses is lost more thoroughly than one filed nowhere.

        `description` is not decoration. It is where the boundary of the theme is written — what
        belongs here and what does not — and it is what you read later to decide where a new
        task goes. A group with a name and nothing else makes that decision wrong every time,
        which is why this asks for it.

        A name already taken in this workspace is refused naming who holds it: two groups called
        the same thing split the same work in half.

        The answer is the whole layout, not a receipt — your own change moved it.

        Args:
            title: The theme, short — "billing", "interface", "infrastructure".
            description: Where the boundary runs: what belongs here, and what goes elsewhere.
                One line, up to 128 characters — it sits under the name in every list. A longer
                one is refused with the count, and nothing is created.
            place_after: A TASKGROUP@ code to put this one directly below. Omit to add at the
                end.
            place_before: A TASKGROUP@ code to put this one directly above.
        """
        active = await require_active()
        clean = _require_title(title)
        await _require_free_title(active, clean)
        anchor = await _anchor(place_after, place_before)
        row = await group_crud.group_create(
            workspace_code=active.code, title=clean, description=description
        )
        await _place(row.code, anchor, place_after)
        return await _layout(active)

    @mcp.tool()
    async def group_update(
        group_code: str,
        title: str | None = None,
        description: str | None = None,
        place_after: str | None = None,
        place_before: str | None = None,
    ) -> AgentGroupList:
        """Update a group — only the fields you pass; anything you omit keeps its value.

        Use it when the person re-words a theme or redraws its boundary. Renaming moves no work:
        tasks are filed by code, and everything in this group stays in it.

        A group in the bin is not updated here — restoring it is the person's to do, and making
        a replacement with the same name leaves them two. Say which one you meant instead.

        Args:
            group_code: The group to change — a TASKGROUP@ code from groups_list.
            title: The theme, short.
            description: Where the boundary runs: what belongs here, and what goes elsewhere.
                Up to 128 characters; a longer one is refused with the count, and nothing in
                this call is applied.
            place_after: A TASKGROUP@ code to move this one directly below.
            place_before: A TASKGROUP@ code to move this one directly above.
        """
        bare = _group_code(group_code)
        active = await require_scope(GROUP_CODE_PREFIX, bare)
        row = await group_crud.group_get(bare, include_deleted=True)
        if row is None:
            raise ValueError(f"{group_code} does not exist in {active.title!r}.")
        if row.deleted_at is not None:
            raise ValueError(
                f"{group_code} is in the bin. Bringing it back is the person's to do — ask for "
                "that rather than creating a second group with the same name."
            )
        clean = None if title is None else _require_title(title)
        if clean is not None:
            await _require_free_title(active, clean, own=bare)
        anchor = await _anchor(place_after, place_before, moving=bare)
        await group_crud.group_update(bare, title=clean, description=description)
        await _place(bare, anchor, place_after)
        return await _layout(active)

    @mcp.tool()
    async def tasks_regroup(group_code: str, task_codes: list[str]) -> AgentTasksRegrouped:
        """File tasks under a group — one call, one intent.

        This is the shape the person asks in: "put these three under billing" — the group first,
        then the work that goes in it. task_update moves one task at a time and is fine for one;
        a batch done that way is several writes, and a batch half-applied looks exactly like a
        batch applied.

        Either every code lands or none does. A code from another workspace, a group in the bin,
        a task that is not there — the call refuses before writing anything and names every code
        at fault, so you repeat it with the list corrected rather than wondering which half went
        through.

        Filing is not the tree. A group says what the work is ABOUT; a parent says what it is
        PART OF — and a part is about the same thing as the whole, so a subtask sits in its
        parent's group. Regrouping an epic takes its subtasks along; a subtask named without its
        parent is refused — file the parent instead.

        Args:
            group_code: A TASKGROUP@ code from groups_list, or an empty string to take these tasks
                out of any group at all.
            task_codes: The TASK@ codes to file there.
        """
        active = await require_active()
        target = _group_code(group_code) if group_code else ""
        if target:
            await require_scope(GROUP_CODE_PREFIX, target)
        if not task_codes:
            raise ValueError("Name at least one TASK@ code — there is nothing to file.")
        if len(task_codes) > REGROUP_CAP:
            raise ValueError(
                f"{len(task_codes)} tasks at once is past the {REGROUP_CAP} this takes. Rebuilding "
                "a layout wholesale is the person's work on their own screen; file the batch "
                "they named."
            )
        bare = [bare_code(code, TASK_CODE_PREFIX) or "" for code in task_codes]
        owners = await task_crud.task_workspace_by_codes(bare)
        faults = [
            f"{tagged(TASK_CODE_PREFIX, code)} is not a live task here"
            if code not in owners
            else f"{tagged(TASK_CODE_PREFIX, code)} belongs to another workspace"
            for code in bare
            if code not in owners or owners[code] != active.code
        ]
        if faults:
            raise ValueError(
                f"Nothing was filed — {'; '.join(faults)}. This session works in "
                f"{active.title!r}; drop those codes or switch workspace and call again."
            )
        moved = await task_crud.task_regroup(bare, target or None)
        layout = await _layout(active)
        return AgentTasksRegrouped(**layout.model_dump(), moved=moved)


__all__ = ["REGROUP_CAP", "register"]
