"""Task note MCP tools — documents written at a task: schemas, breakdowns, concepts.

The agent works with a TASK note, not a free-standing document: it is created with its task,
lives in that task's workspace and is reached through it. So the tools are ``task_note_*``, the
way stages are ``stage_*`` and the journal ``journal_*``. The code is ``NOTE@`` — the name of the
``notes`` module's entity, not of the place it sits in.

The text itself is edited by ``content_*`` with the field ``body``; here are creating it, reading
it whole, and the two short fields that are not content.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.modules.notes.crud import note as notes_crud
from src.modules.notes.models.note import Note
from src.modules.tasks.codes import bare_code
from src.modules.tasks.constants import NOTE_CODE_PREFIX, TASK_CODE_PREFIX
from src.modules.tasks.crud import note as note_crud
from src.modules.tasks.crud import task as task_crud
from src.modules.tasks.dto import AgentTaskNote, AgentTaskNoteCreated, AgentTaskNoteUpdated
from src.modules.tasks.mcp.content.base import deleted_task_refusal
from src.modules.tasks.mcp.scope import require_scope
from src.modules.workspace.models.workspace import Workspace

if TYPE_CHECKING:  # fastmcp fork — backend only (via mcp_server(ctx))
    from fastmcp import FastMCP


async def require_live_task(task_code: str) -> None:
    """A write to a task note is a write to its task: a deleted task refuses it like any other."""
    if await task_crud.task_get(task_code) is None:
        raise ValueError(deleted_task_refusal(task_code))


async def _task_note(note_code: str, *, writing: bool) -> tuple[Workspace, str, Note]:
    """The fenced workspace, the owning task and the live note — or a refusal.

    A note no task holds, and a deleted one, do not exist for the agent: the first is not a task
    note at all, the second is the person's to restore. A note of a deleted task reads, and does
    not take writes.
    """
    bare = bare_code(note_code, NOTE_CODE_PREFIX) or ""
    active = await require_scope(NOTE_CODE_PREFIX, bare)
    task_code = await note_crud.task_note_task(bare)
    note = await notes_crud.note_get(bare) if task_code else None
    if task_code is None or note is None:
        raise ValueError(f"Task note {NOTE_CODE_PREFIX}@{bare} does not exist (or is deleted).")
    if writing:
        await require_live_task(task_code)
    return active, task_code, note


def register(mcp: "FastMCP") -> None:

    @mcp.tool()
    async def task_note_add(
        task_code: str, title: str, description: str | None = None, body: str | None = None
    ) -> AgentTaskNoteCreated:
        """Add a note to a task — a document written while working out how to do it.

        A note is for what the plan cannot hold: a data schema, a comparison of options, a
        concept, a table someone will come back to. The plan says how you will do the work and
        which files it touches; a note is the material behind it. If a paragraph in the plan
        would do, it is not a note.

        The note belongs to this task alone. Write the text now or later with
        content_set(code, "body", …) and its neighbours; task_get lists the task's notes without
        their text, task_note_get reads one whole.

        Args:
            task_code: The task the note belongs to — a TASK@ code, of any type.
            title: What the document is, one line.
            description: What it is about and when to open it — the line a reader decides by.
            body: The document, markdown — skill_get('markdown'). Over 65536 characters is
                refused, not trimmed.
        """
        bare = bare_code(task_code, TASK_CODE_PREFIX) or ""
        active = await require_scope(TASK_CODE_PREFIX, bare)
        note = await note_crud.task_note_add(
            task_code=bare, title=title, description=description, body=body
        )
        return AgentTaskNoteCreated(
            workspace=active.code, workspace_title=active.title, code=note.code
        )

    @mcp.tool()
    async def task_note_get(note_code: str) -> AgentTaskNote:
        """Read one task note whole — its text and the task it belongs to.

        task_get lists a task's notes by title and description only; open the one you need here.

        Args:
            note_code: The note to read — a NOTE@ code from task_get or task_note_add.
        """
        active, task_code, note = await _task_note(note_code, writing=False)
        return AgentTaskNote(
            workspace=active.code,
            workspace_title=active.title,
            code=note.code,
            task_code=task_code,
            title=note.title,
            description=note.description,
            body=note.body,
            updated_at=note.updated_at,
        )

    @mcp.tool()
    async def task_note_update(
        note_code: str, title: str | None = None, description: str | None = None
    ) -> AgentTaskNoteUpdated:
        """Rename a task note or re-word what it is about — only the fields you pass.

        The text is not here: it is content, edited in place by content_set / content_replace /
        content_set_section / content_add with the field "body".

        Args:
            note_code: The note to change — a NOTE@ code.
            title: New one-line name.
            description: New "what it is about and when to open it"; an empty string clears it.
        """
        active, task_code, note = await _task_note(note_code, writing=True)
        row = await notes_crud.note_update(note.code, title=title, description=description)
        if row is None:
            raise ValueError(
                f"Task note {NOTE_CODE_PREFIX}@{note.code} does not exist (or is deleted)."
            )
        return AgentTaskNoteUpdated(
            workspace=active.code,
            workspace_title=active.title,
            code=row.code,
            task_code=task_code,
            title=row.title,
            description=row.description,
            updated_at=row.updated_at,
        )


__all__ = ["register"]
