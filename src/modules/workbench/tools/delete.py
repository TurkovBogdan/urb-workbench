"""The delete MCP tool — one door for every type; the code itself picks the cascade.

Five separate tools of one line of code each would cost the agent five descriptions in context,
while they differ in exactly one thing — the cascade, which is bound to the type and described
here in a single list.

Types that have no deletion hit a refusal that names the reason and what to do instead. The
refusal here is not "forbidden" but a teaching channel: a journal entry is history that stays,
the layout belongs to the person, and the irreversible stays with the person too.

What a type deletes, and whether its code is visible from here, is its handler's
(``contracts.Deletable``) — registered in ``DELETABLE`` by prefix; the order there is the order
the refusal lists the types in.

``holder`` exists for a type held in several places at once (``contracts.Detachable`` — a file):
it names the one place to take the entity out of. Any other type refuses it before anything is
read, so a stray argument never turns into a deletion of something else.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.modules.tasks.constants import GROUP_CODE_PREFIX, JOURNAL_CODE_PREFIX
from src.modules.workbench.codes import bare_code, code_prefix
from src.modules.workbench.contracts import Deletable, Detachable, by_prefix
from src.modules.workbench.entities.codex import CodexDeletion
from src.modules.workbench.entities.file import FileDeletion, as_file_code
from src.modules.workbench.entities.tasks import NoteDeletion, StageDeletion, TaskDeletion
from src.modules.workbench.scope import require_visible
from src.modules.workspace.constants import WORKSPACE_CODE_PREFIX

if TYPE_CHECKING:  # fastmcp fork — backend only (via mcp_server(ctx))
    from fastmcp import FastMCP

DELETABLE: dict[str, Deletable] = by_prefix(
    TaskDeletion(), StageDeletion(), NoteDeletion(), CodexDeletion(), FileDeletion()
)

# Why not — per type. The text reaches the agent as is, so it names the way out, not the ban.
DELETE_REFUSALS: dict[str, str] = {
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
    async def delete(code: str, holder: str | None = None) -> bool:
        """Delete one entity. The code decides what goes, and what goes with it.

        TASK@ — the task and the whole branch under it, reversibly: it goes to the bin, and a
        person can bring it back. You cannot: restoring is theirs, so say so rather than
        creating a replacement.
        STAGE@ — removed outright, with the files attached at it: they leave the task, and their
        codes in any text stop resolving. Attach a file to the task itself to keep it past the
        stage. A plan has no hidden steps; a step you decided against is closed with
        stage_close(outcome="canceled"), which keeps why. Deleting leaves a gap in the
        numbering, and that is fine — numbers order the plan, they do not count it.
        NOTE@ — the task note, reversibly: it leaves the task's list, and a person can bring it
        back. Its files stay in the task.
        CODEX@ — a codex note, reversibly, and only alone: one with child notes is refused with
        their list — delete those first. Only where the mount lets you write; a codex itself is
        the person's.
        FILE@ — the file is taken out of its place here: its binding goes, and the stored bytes
        go once nothing holds them. Held in one place here, that one; held in several, the call
        refuses, changes nothing and lists them — repeat with `holder` naming the place. Taking
        a file out of a codex note needs the mount's write right, out of a task a live task.

        A journal entry is not deletable, and neither is a group or a workspace.

        Args:
            code: The entity to delete — a TASK@, STAGE@, NOTE@, CODEX@ (a note) or FILE@ code
                (an IMAGE@ names the same file).
            holder: FILE@ only — the place to take the file out of: a TASK@ or a CODEX@ note.
                A NOTE@ or STAGE@ names its task: the file leaves the whole task, wherever in it
                it was brought in. There is no taking a file out of a note alone.
        """
        code = as_file_code(code)
        prefix = code_prefix(code)
        refusal = DELETE_REFUSALS.get(prefix)
        if refusal is not None:
            raise ValueError(refusal)
        handler = DELETABLE.get(prefix)
        if holder and handler is not None and not isinstance(handler, Detachable):
            raise ValueError(
                f"`holder` names the place to take a file out of — a {prefix}@ is held in one "
                f"place only. Call delete({code!r}) without it."
            )
        if handler is None and not prefix and "/" in code:
            raise ValueError(
                f"{code!r} looks like a codex path — delete takes the note's CODEX@ code; "
                f"codex_get([{code!r}]) returns it."
            )
        if handler is None:
            raise ValueError(
                f"{code!r} is not something this deletes — pass a "
                f"{' or '.join(f'{p}@' for p in DELETABLE)} code."
            )
        bare = bare_code(code, prefix) or ""
        await require_visible(handler, bare)
        if holder and isinstance(handler, Detachable):
            return await handler.detach(bare, holder)
        return await handler.delete(bare)


__all__ = ["DELETABLE", "DELETE_REFUSALS", "register"]
