"""The delete MCP tool — one door for every type; the code itself picks the cascade.

Five separate tools of one line of code each would cost the agent five descriptions in context,
while they differ in exactly one thing — the cascade, which is bound to the type and described
here in a single list.

Types that have no deletion hit a refusal that names the reason and what to do instead. The
refusal here is not "forbidden" but a teaching channel: a journal entry is history that stays,
the layout belongs to the person, and the irreversible stays with the person too.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.modules.tasks.codes import bare_code, code_prefix
from src.modules.tasks.constants import (
    GROUP_CODE_PREFIX,
    JOURNAL_CODE_PREFIX,
    NOTE_CODE_PREFIX,
    STAGE_CODE_PREFIX,
    TASK_CODE_PREFIX,
)
from src.modules.notes.crud import note as notes_crud
from src.modules.tasks.crud import note as note_crud
from src.modules.tasks.crud import stage as stage_crud
from src.modules.tasks.crud import task as task_crud
from src.modules.tasks.mcp.scope import require_scope
from src.modules.tasks.mcp.task_note import require_live_task
from src.modules.workspace.constants import WORKSPACE_CODE_PREFIX

if TYPE_CHECKING:  # fastmcp fork — backend only (via mcp_server(ctx))
    from fastmcp import FastMCP

_DELETABLE = (TASK_CODE_PREFIX, STAGE_CODE_PREFIX, NOTE_CODE_PREFIX)

# Why not — per type. The text reaches the agent as is, so it names the way out, not the ban.
_REFUSALS = {
    JOURNAL_CODE_PREFIX: (
        "A journal entry is not deleted — it is the history of how the work went, and a gap in "
        "it answers nothing. Changed your mind: write a new entry pointing at the old one; "
        "detail to add goes to its body with content_add(code, \"body\", …)."
    ),
    GROUP_CODE_PREFIX: (
        "Removing a group is the person's to do: it decides what happens to the tasks filed "
        "there — left without a group, moved to another, or binned with it — and bringing it "
        "back is theirs as well. Re-word the theme with group_update, or empty it with "
        "tasks_regroup(group_code=\"\", …) and leave the empty group for them to clear."
    ),
    WORKSPACE_CODE_PREFIX: (
        "A workspace holds everything else here, and deleting it is the person's call. "
        "workspace_use switches the one you work in."
    ),
}


def register(mcp: "FastMCP") -> None:

    @mcp.tool()
    async def delete(code: str) -> bool:
        """Delete one entity. The code decides what goes, and what goes with it.

        TASK@ — the task and the whole branch under it, reversibly: it goes to the bin, and a
        person can bring it back. You cannot: restoring is theirs, so say so rather than
        creating a replacement.
        STAGE@ — removed outright. A plan has no hidden steps; a step you decided against is
        closed with stage_close(outcome="canceled"), which keeps why. Deleting leaves a gap in
        the numbering, and that is fine — numbers order the plan, they do not count it.
        NOTE@ — the task note, reversibly: it leaves the task's list, and a person can bring it
        back.

        A journal entry is not deletable, and neither is a group or a workspace.

        Args:
            code: The entity to delete — a TASK@, STAGE@ or NOTE@ code.
        """
        prefix = code_prefix(code)
        refusal = _REFUSALS.get(prefix)
        if refusal is not None:
            raise ValueError(refusal)
        if prefix not in _DELETABLE:
            raise ValueError(
                f"{code!r} is not something this deletes — pass a "
                f"{' or '.join(f'{p}@' for p in _DELETABLE)} code."
            )
        bare = bare_code(code, prefix) or ""
        await require_scope(prefix, bare)
        if prefix == TASK_CODE_PREFIX:
            return await task_crud.task_delete(bare)
        if prefix == NOTE_CODE_PREFIX:
            # A note held by no task is not a task note: from here it does not exist.
            task_code = await note_crud.task_note_task(bare)
            if task_code is None:
                return False
            await require_live_task(task_code)
            return await notes_crud.note_delete(bare)
        return await stage_crud.stage_delete(bare)


__all__ = ["register"]
