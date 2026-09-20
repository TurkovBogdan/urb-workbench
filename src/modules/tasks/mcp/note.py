"""MCP-тулы журнала работы.

Вид записи агент выбирает из трёх: ``decision`` / ``finding`` / ``fact``. ``remark`` в
перечислении нет — замечание пишет постановщик, и инструмента с этим типом у агента не
существует: обе половины записи, написанные одной рукой, превращают шлюз в самооценку.

Порядок значений — от частого к редкому: первое значение перечисления модель выбирает заметно
чаще прочих, и частый вид должен стоять раньше редкого.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.modules.tasks.codes import bare_code
from src.modules.tasks.constants import (
    NOTE_CODE_PREFIX,
    NOTE_REMARK,
    NOTE_TYPES,
    NOTE_TYPES_BY_AGENT,
    STAGE_CODE_PREFIX,
    TASK_CODE_PREFIX,
)
from src.modules.tasks.crud import note as note_crud
from src.modules.tasks.dto import AgentNoteCreated, AgentNoteList, AgentNoteRow
from src.modules.tasks.mcp.scope import require_scope

if TYPE_CHECKING:  # fork fastmcp — только backend (через mcp_server(ctx))
    from fastmcp import FastMCP


def register(mcp: "FastMCP") -> None:

    @mcp.tool()
    async def note_add(
        task_code: str,
        type: str,
        title: str,
        body: str | None = None,
        stage_code: str | None = None,
    ) -> AgentNoteCreated:
        """Record something in this task's journal — a decision, a finding or a fact.

        The journal is append-only. An entry is never rewritten and never deleted; changing your
        mind is a new entry. Pick the kind by what the line IS:

        `decision` — a choice you made along the way, and what it rests on. Leave it open until
        it rests on something: an open decision is what an assumption looks like here, and being
        able to see them is the point.
        `finding` — something broken or owed that you noticed OUTSIDE this task. Without
        somewhere to put it the moment you see it, it dies with the session and gets paid for
        again next time. It does not hold up your hand-over — a person triages it.
        `fact` — a number, a path, an exact name, the reason something failed. Closed the moment
        it is written; it is waiting for nobody.

        A remark from the requester is theirs to write, not yours.

        Args:
            task_code: The task this belongs to — a TASK@ code. The task needs a journal:
                a `simple` one refuses, and says to raise its type first.
            type: decision / finding / fact.
            title: The point in one line.
            body: The detail — options weighed, what you saw, where.
            stage_code: The STAGE@ this came up in, if it was one step and not the whole task.
        """
        bare = bare_code(task_code, TASK_CODE_PREFIX) or ""
        active = await require_scope(TASK_CODE_PREFIX, bare)
        if type == NOTE_REMARK:
            raise ValueError(
                "A remark is the requester's word about your work, and writing it yourself "
                "would make the entry answer to nobody. What you noticed is a `finding`; what "
                "you decided is a `decision`."
            )
        if type not in NOTE_TYPES_BY_AGENT:
            raise ValueError(
                f"Unknown entry type {type!r}; expected one of "
                f"{', '.join(NOTE_TYPES_BY_AGENT)}."
            )
        row = await note_crud.note_create(
            task_code=bare,
            type=type,
            title=title,
            body=body,
            stage_code=bare_code(stage_code, STAGE_CODE_PREFIX),
        )
        return AgentNoteCreated(
            workspace=active.code, workspace_title=active.title, code=row.code
        )

    @mcp.tool()
    async def note_resolve(note_code: str, resolution: str) -> AgentNoteRow:
        """Close a journal entry with what settled it.

        Once only: the journal is append-only, and a resolution rewritten after the fact turns
        the history into a story about how it was always going to work. Changed your mind — new
        entry.

        A decision is settled by what it now rests on: the requester's answer, or your own check
        with the pointer to it. A remark is settled by how you took it into account.

        Args:
            note_code: The entry to close — a NOTE@ code.
            resolution: What was decided, how it was taken into account, or what the answer
                turned out to be.
        """
        bare = bare_code(note_code, NOTE_CODE_PREFIX) or ""
        await require_scope(NOTE_CODE_PREFIX, bare)
        row = await note_crud.note_resolve(bare, resolution)
        if row is None:
            raise ValueError(f"Entry {note_code} does not exist.")
        return AgentNoteRow.model_validate(row)

    @mcp.tool()
    async def notes_list(
        task_code: str, type: str | None = None, open_only: bool = False
    ) -> AgentNoteList:
        """Read a task's journal, oldest first.

        task_get already gives you what is still open; this is for the history behind it — why
        the work is shaped the way it is, and what was tried and dropped.

        Args:
            task_code: The task whose journal to read — a TASK@ code.
            type: decision / remark / finding / fact, to see one kind only.
            open_only: Only the entries nothing has settled yet.
        """
        bare = bare_code(task_code, TASK_CODE_PREFIX) or ""
        active = await require_scope(TASK_CODE_PREFIX, bare)
        if type is not None and type not in NOTE_TYPES:
            raise ValueError(
                f"Unknown entry type {type!r}; expected one of {', '.join(NOTE_TYPES)}."
            )
        rows = await note_crud.note_list_by_task(bare, type=type, open_only=open_only)
        return AgentNoteList(
            workspace=active.code,
            workspace_title=active.title,
            notes=[AgentNoteRow.model_validate(row) for row in rows],
        )


__all__ = ["register"]
