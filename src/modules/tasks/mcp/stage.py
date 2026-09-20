"""MCP-тулы этапов плана.

Три инструмента, и их трое из-за одного: **закрытие требует доказательства, и требует его
схема**. Отказ на записи агент увидел бы после попытки; обязательный аргумент не даёт собрать
вызов вовсе — разница между третьим рычагом и первым.

Остальное поделено по тому же признаку: ``stage_update`` двигает этап между нетерминальными
состояниями и правит его карточку, ``stage_close`` уводит в терминальное. Смешай их — и
обязательность доказательства пришлось бы проверять по значению другого аргумента, то есть
вернуть на запись то, что сейчас стоит в схеме.
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

if TYPE_CHECKING:  # fork fastmcp — только backend (через mcp_server(ctx))
    from fastmcp import FastMCP

# Состояния, между которыми этап двигают правкой. Терминальные сюда не входят — за ними
# ``stage_close``, и это единственная дверь, за которой спрашивают доказательство.
STAGE_OPEN_STATUSES = (STATUS_PLANNED, STATUS_IN_PROGRESS)
STAGE_OUTCOMES = (STATUS_DONE, STATUS_CANCELED)


def _stage_code(value: str) -> str:
    return bare_code(value, STAGE_CODE_PREFIX) or ""


async def _changed(stage, active) -> AgentStageChanged:
    """Ответ правки этапа: сам этап плюс статус ЗАДАЧИ.

    Старт этапа задачу не двигает — это разные вопросы, ход исполнения против жизненного цикла
    карточки. Но разойтись они могут молча, и тогда «в работе» по этапам соседствует с
    «в очереди» по задаче, а заметить это неоткуда. Строка в ответе и есть это «откуда».
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

        A stage that has not started can be rewritten freely; once it is running, the plan
        behind you is frozen — changing it is a new entry in the journal and a new stage after
        it.

        Args:
            task_code: The task this stage belongs to — a TASK@ code. Stages belong to
                `extended` tasks only; anything else refuses and says so. A `standard` task
                carries its plan as prose in the body — write it there, or raise the type if
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

        Two things are not here. The text of the stage is a body — body_set and its neighbours
        own it, and they refuse once the stage is running. Closing is stage_close, which
        requires the proof. Status here only moves it between planned and in_progress.

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
        # Доказательство записывается ДО перевода статуса: шлюз в CRUD смотрит на колонку, и
        # обратный порядок упёрся бы в собственную проверку.
        await stage_crud.stage_update(bare, evidence=evidence)
        row = await stage_crud.stage_update_status(bare, outcome)
        if row is None:
            raise ValueError(f"Stage {stage_code} does not exist.")
        return await _changed(row, active)


__all__ = ["STAGE_OPEN_STATUSES", "STAGE_OUTCOMES", "register"]
