"""Plan stage MCP tools.

Three tools, and there are three because of one thing: **closing requires evidence, and the
schema is what requires it**. A refusal on write the agent would only see after trying; a
required argument does not let the call be assembled at all — the difference between the third
lever and the first.

The rest is split along the same line: ``stage_update`` moves a stage between non-terminal
states and edits its card, ``stage_close`` takes it to a terminal one. Merge them and the
evidence requirement would have to be checked against the value of another argument — that is,
moved back to the write what now sits in the schema.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.modules.tasks.codes import bare_code
from src.modules.tasks.constants import (
    STAGE_CODE_PREFIX,
    STATUS_CANCELED,
    STATUS_DONE,
    STATUS_IN_PROGRESS,
    STATUS_PLANNED,
    TASK_CODE_PREFIX,
)
from src.modules.tasks.crud import stage as stage_crud
from src.modules.tasks.crud import task as task_crud
from src.modules.tasks.dto import AgentStageChanged, AgentStageCreated, AgentStageRow
from src.modules.tasks.mcp.scope import require_scope

if TYPE_CHECKING:  # fastmcp fork — backend only (via mcp_server(ctx))
    from fastmcp import FastMCP

# States a stage is moved between by an edit. Terminal ones are not here — they are behind
# ``stage_close``, the only door where evidence is asked for.
STAGE_OPEN_STATUSES = (STATUS_PLANNED, STATUS_IN_PROGRESS)
STAGE_OUTCOMES = (STATUS_DONE, STATUS_CANCELED)


def _stage_code(value: str) -> str:
    return bare_code(value, STAGE_CODE_PREFIX) or ""


async def _changed(stage, active) -> AgentStageChanged:
    """The reply to a stage edit: the stage itself plus the TASK's status.

    Starting a stage does not move the task — these are different questions, execution progress
    versus the card's lifecycle. But they can drift apart silently, and then "in progress" by
    stages sits next to "queued" by the task, with nothing to notice it by. That line in the
    reply is the something to notice it by.
    """
    task = await task_crud.task_get(stage.task_code, include_deleted=True)
    return AgentStageChanged(
        workspace=active.code,
        workspace_title=active.title,
        stage=AgentStageRow.model_validate(stage),
        task_code=stage.task_code,
        task_status=task.status if task else "",
    )


def register(mcp: "FastMCP") -> None:

    @mcp.tool()
    async def stage_add(
        task_code: str,
        title: str,
        description: str | None = None,
        body: str | None = None,
        number: int | None = None,
    ) -> AgentStageCreated:
        """Add a stage to a task's plan — one step, with its own state and its own proof.

        A stage is a unit of work done in one go. As soon as a step needs its own acceptance, it
        is not a stage but a subtask: create it with task_create(parent_code=…) instead.

        Numbers order the plan, they do not count it. Deleting a stage leaves a gap, and that is
        fine — do not renumber to close it: you refer to "the third stage" in the journal, and a
        silent shift would make those references false.

        Its body stays editable on any status — content_set(code, "body", …) and its
        neighbours. Clarifying a step is fine; changing what a step behind you promised is a
        decision in the journal and a new stage after it, not a re-worded one.

        Args:
            task_code: The task this stage belongs to — a TASK@ code. Stages belong to
                `extended` tasks only; anything else refuses and says so. A `standard` task
                carries its plan as prose in `plan` — write it there, or raise the type if
                the work really needs steps with their own evidence.
            title: What this step is, one line.
            description: What it is about, and whether the body needs reading at all.
            body: The work in full, markdown.
            number: Position in the plan. Omit for next in line. A number already taken is
                refused naming who holds it — move that one first, or leave numbering alone.
        """
        bare = bare_code(task_code, TASK_CODE_PREFIX) or ""
        active = await require_scope(TASK_CODE_PREFIX, bare)
        row = await stage_crud.stage_create(
            task_code=bare,
            title=title,
            number=number,
            description=description,
            body=body,
        )
        return AgentStageCreated(
            workspace=active.code,
            workspace_title=active.title,
            code=row.code,
            number=row.number,
        )

    @mcp.tool()
    async def stage_update(
        stage_code: str,
        title: str | None = None,
        description: str | None = None,
        number: int | None = None,
        status: str | None = None,
    ) -> AgentStageChanged:
        """Update a stage — only the fields you pass.

        Two things are not here. The text of the stage is content — content_set(code, "body",
        …) and its neighbours own it. Closing is stage_close, which requires the proof. Status
        here only moves it between planned and in_progress.

        Starting a stage does not start the task — they answer different questions, so the
        answer tells you where the task itself stands and the two do not drift apart unnoticed.

        Args:
            stage_code: The stage to change — a STAGE@ code.
            title: New one-line name.
            description: New short "what this is about".
            number: New position. A number already taken is refused naming who holds it.
            status: planned / in_progress.
        """
        bare = _stage_code(stage_code)
        active = await require_scope(STAGE_CODE_PREFIX, bare)
        if status is not None and status not in STAGE_OPEN_STATUSES:
            raise ValueError(
                f"{status!r} is not something a stage is moved to from here — this tool only "
                f"goes between {' and '.join(STAGE_OPEN_STATUSES)}. A stage is finished (or "
                "abandoned) with stage_close, which asks for the proof."
            )
        row = await stage_crud.stage_update(
            bare, title=title, description=description, number=number
        )
        if row is None:
            raise ValueError(f"Stage {stage_code} does not exist.")
        if status is not None:
            row = await stage_crud.stage_update_status(bare, status)
        return await _changed(row, active)

    @mcp.tool()
    async def stage_close(
        stage_code: str, evidence: str, outcome: str = STATUS_DONE
    ) -> AgentStageChanged:
        """Close a stage — with the pointer to what proves it.

        `evidence` is a pointer, not a story: the command and its result, the path to what
        changed, a summary of the diff. "Done" and "it works now" are exactly what this argument
        exists to prevent — a step marked finished with no trace makes every step after it
        reason on a claim nobody checked.

        Args:
            stage_code: The stage to close — a STAGE@ code.
            evidence: The proof — a command and its outcome, a path, a diff summary. Kept short
                on purpose: a command's full output does not belong here, a pointer to it does.
            outcome: done (default) or canceled. A canceled stage takes evidence too — why it
                was abandoned is worth the same line.
        """
        bare = _stage_code(stage_code)
        active = await require_scope(STAGE_CODE_PREFIX, bare)
        if outcome not in STAGE_OUTCOMES:
            raise ValueError(
                f"outcome must be one of {', '.join(STAGE_OUTCOMES)} — this tool ends a stage. "
                "Use stage_update to move it between planned and in_progress."
            )
        if not evidence.strip():
            raise ValueError(
                "evidence is empty. Closing a stage means saying what shows it happened — a "
                "command and its result, a path, a diff summary. Whitespace does not count."
            )
        # Evidence is written BEFORE the status change: the gate in CRUD looks at the column, and
        # the reverse order would run into its own check.
        await stage_crud.stage_update(bare, evidence=evidence)
        row = await stage_crud.stage_update_status(bare, outcome)
        if row is None:
            raise ValueError(f"Stage {stage_code} does not exist.")
        return await _changed(row, active)


__all__ = ["STAGE_OPEN_STATUSES", "STAGE_OUTCOMES", "register"]
