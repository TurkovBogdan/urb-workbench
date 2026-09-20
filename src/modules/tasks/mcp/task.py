"""MCP-тулы задачи — основная поверхность работы агента.

Пять инструментов на четыре сценария: найти, прочитать целиком, завести, изменить, сдвинуть по
жизненному циклу. Разводить их мельче незачем, сливать — некуда: у смены статуса своё правило
(отметка фазы и недоступность терминальных значений), у правки своё (постановку чужой задачи
трогать нельзя).

Ни один из них не принимает пространства: оно у сессии (``workspace/mcp/session.py``), и код из
чужого отвергается забором (``scope.py``).
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from src.modules.tasks.codes import bare_code
from src.modules.tasks.constants import (
    ACTOR_AGENT,
    GROUP_CODE_PREFIX,
    NOTE_TYPES_BLOCKING,
    STATUS_CANCELED,
    STATUS_DONE,
    TASK_CODE_PREFIX,
    TASK_PRIORITIES,
    TASK_STATUSES,
    TASK_STATUSES_TERMINAL,
    TASK_TYPE_DEFAULT,
    TASK_TYPES,
)
from src.modules.tasks.crud import group as group_crud
from src.modules.tasks.crud import link as link_crud
from src.modules.tasks.crud import note as note_crud
from src.modules.tasks.crud import stage as stage_crud
from src.modules.tasks.crud import task as task_crud
from src.modules.tasks.dto import (
    AgentNoteRow,
    AgentStageRow,
    AgentTaskCreated,
    AgentTaskDetail,
    AgentTaskList,
    AgentTaskRow,
    AgentTaskStatus,
)
from src.modules.tasks.mcp.scope import require_active, require_scope

if TYPE_CHECKING:  # fork fastmcp — только backend (через mcp_server(ctx))
    from fastmcp import FastMCP

# Потолок выдачи списка. Стоит здесь, а не аргументом тула: поле в схеме оплачивается каждым
# вызовом, а нужно оно в одном случае из двадцати — и тогда разрыв ``shown``/``total`` скажет
# о нём внятнее, чем умолчание, которого агент не видел.
LIST_CAP = 50

# Агрегаты статуса рядом с семью настоящими. Отрицание («не done и не canceled») в перечислении
# не выразить, а спрашивают про него чаще всего — поэтому у него есть имя.
STATUS_UNFINISHED = "unfinished"
STATUS_ANY = "any"

# Терминальные статусы агенту недоступны. ``done`` — потому что принимает работу постановщик, и
# это прямое следствие самого частого режима отказа: объявлять победу раньше времени.
# ``canceled`` — потому что решение «работы не будет» не принимают изнутри работы.
AGENT_STATUSES = tuple(s for s in TASK_STATUSES if s not in TASK_STATUSES_TERMINAL)

_UNFINISHED = AGENT_STATUSES


def _task_code(value: str) -> str:
    return bare_code(value, TASK_CODE_PREFIX) or ""


def _checked(value: str, allowed: tuple[str, ...], what: str) -> str:
    if value not in allowed:
        raise ValueError(f"Unknown {what} {value!r}; expected one of {', '.join(allowed)}.")
    return value


async def _rows(tasks: list) -> list[AgentTaskRow]:
    """Строки скана: поля задачи + место в дереве, одним запросом на весь список."""
    codes = [task.code for task in tasks]
    links = await link_crud.link_map_by_task_codes(codes)
    children = await link_crud.link_child_count_by_parent_codes(codes)
    return [
        AgentTaskRow(
            code=task.code,
            title=task.title,
            description=task.description,
            status=task.status,
            priority=task.priority,
            type=task.type,
            group_code=task.group_code,
            parent_code=links[task.code].parent_code if task.code in links else None,
            has_children=children.get(task.code, 0) > 0,
            deadline_at=task.deadline_at,
        )
        for task in tasks
    ]


def register(mcp: "FastMCP") -> None:

    @mcp.tool()
    async def tasks_list(
        status: str = STATUS_UNFINISHED,
        group_code: str | None = None,
        query: str | None = None,
    ) -> AgentTaskList:
        """Find tasks in the workspace this session works in — the scan layer, one line each.

        Start here when you do not know what exists. The answer carries no brief and no plan:
        that is what task_get is for, and pulling it for a whole list would cost more than
        reading the list twice.

        By default only unfinished work comes back — finished tasks are history, and they would
        crowd out what is in flight. Subtasks come in the same flat list as their parents, each
        carrying `parent_code`: a row with one is part of somebody else's work, not a job of its
        own. If `shown` is less than `total`, narrow with status, group_code or query rather
        than asking again.

        Args:
            status: unfinished (default — everything not done or canceled) / any / backlog /
                planned / in_progress / in_test / in_review / done / canceled.
            group_code: A GROUP@ code for one theme; an empty string for the tasks filed in no
                group at all; omit to see every group.
            query: Case-insensitive substring of the title or the goal. Omit to filter only.
        """
        active = await require_active()
        wanted: tuple[str, ...] | None = None
        exact: str | None = None
        if status == STATUS_UNFINISHED:
            wanted = _UNFINISHED
        elif status != STATUS_ANY:
            exact = _checked(status, TASK_STATUSES, "status")
        rows = await task_crud.task_list_by_workspace(
            active.code,
            status=exact,
            statuses=wanted,
            query=query,
            group_code=bare_code(group_code, GROUP_CODE_PREFIX),
        )
        return AgentTaskList(
            workspace=active.code,
            workspace_title=active.title,
            tasks=await _rows(rows[:LIST_CAP]),
            shown=min(len(rows), LIST_CAP),
            total=len(rows),
        )

    @mcp.tool()
    async def task_get(task_code: str) -> AgentTaskDetail:
        """Read one task in full — the brief, the plan, its stages, and what is still open.

        This is the working view: what you need before touching the work, and nothing you would
        have to ask twice for. Read it before you start and after anyone else has been here —
        the brief is the requester's, and it is the only place that says what "done" means here.

        Closed journal entries are not included, only their count: they answer "how was this
        decided", which is a separate question — notes_list when you have it.

        Args:
            task_code: The task to read — a TASK@ code from tasks_list.
        """
        bare = _task_code(task_code)
        active = await require_scope(TASK_CODE_PREFIX, bare)
        task = await task_crud.task_get(bare, include_deleted=True)
        if task is None:
            raise ValueError(f"Task {task_code} does not exist.")
        link = await link_crud.link_get(bare)
        parent = (
            await task_crud.task_get(link.parent_code, include_deleted=True)
            if link and link.parent_code
            else None
        )
        group = (
            await group_crud.group_get(task.group_code, include_deleted=True)
            if task.group_code
            else None
        )
        children = await task_crud.task_list_by_parent(bare)
        stages = await stage_crud.stage_list_by_task(bare)
        notes = await note_crud.note_list_by_task(bare)
        open_notes = [note for note in notes if not note.resolution]
        return AgentTaskDetail(
            workspace=active.code,
            workspace_title=active.title,
            code=task.code,
            title=task.title,
            description=task.description,
            context=task.context,
            constraints=task.constraints,
            criteria=task.criteria,
            body=task.body,
            status=task.status,
            priority=task.priority,
            type=task.type,
            created_by=task.created_by,
            group_code=task.group_code,
            group_title=group.title if group else "",
            parent_code=parent.code if parent else None,
            parent_title=parent.title if parent else "",
            deadline_at=task.deadline_at,
            started_at=task.started_at,
            completed_at=task.completed_at,
            canceled_at=task.canceled_at,
            children=await _rows(children),
            stages=[AgentStageRow.model_validate(stage) for stage in stages],
            open_notes=[AgentNoteRow.model_validate(note) for note in open_notes],
            closed_notes=len(notes) - len(open_notes),
            unfinished_stages=sum(
                1 for stage in stages if stage.status not in TASK_STATUSES_TERMINAL
            ),
        )

    @mcp.tool()
    async def task_create(
        title: str,
        description: str,
        context: str | None = None,
        constraints: str | None = None,
        criteria: str | None = None,
        type: str = TASK_TYPE_DEFAULT,
        priority: str | None = None,
        group_code: str | None = None,
        parent_code: str | None = None,
        deadline_at: datetime | None = None,
    ) -> AgentTaskCreated:
        """Create a task in the workspace this session works in.

        Write the goal, not the steps: `description` says what becomes true when the work is
        done, and whoever runs it picks the path. Steps belong in the plan — and the plan is
        written after the code has been read, which is why it cannot be set here.

        For anything past a one-liner, fill the brief. `context` points at what the code does
        not say. `constraints` says what must not be touched. `criteria` lists conditions that
        can be checked one by one — without them, "done" gets decided by whoever ran the work.

        Subtask: pass `parent_code`. File it under a theme with `group_code` — groups_list says
        what the themes are and where their boundaries run. A new task starts in `backlog`;
        move it with task_status when you actually pick it up.

        Args:
            title: Short name — the line this task is found by in a list.
            description: The goal: what becomes true when the work is done. One paragraph, an
                outcome rather than a sequence of steps.
            context: What cannot be derived from the code — a decision and its reason, a
                reference implementation, a domain term. Markdown.
            constraints: What may change, what to ask about first, what must never be touched.
            criteria: Checkable conditions of done, one per line, each with what proves it.
            type: simple (a title and a goal, nothing else) / standard (brief, plan as prose,
                journal) / extended (all of that plus stages — the plan broken into steps, each
                closed with its own evidence). Pick extended when the work outlasts one sitting;
                a standard task refuses stages and says so.
            priority: burning / high / normal / low / frozen. Default normal.
            group_code: A GROUP@ code from groups_list; omit to leave it unfiled.
            parent_code: A TASK@ code to make this a subtask of it.
            deadline_at: Hard deadline, `YYYY-MM-DD HH:MM:SS` in UTC.
        """
        active = await require_active()
        _checked(type, TASK_TYPES, "type")
        if priority is not None:
            _checked(priority, TASK_PRIORITIES, "priority")
        parent_bare = bare_code(parent_code, TASK_CODE_PREFIX)
        if parent_bare:
            await require_scope(TASK_CODE_PREFIX, parent_bare)
        group_bare = bare_code(group_code, GROUP_CODE_PREFIX)
        if group_bare:
            await require_scope(GROUP_CODE_PREFIX, group_bare)
        row = await task_crud.task_create(
            workspace_code=active.code,
            title=title,
            description=description,
            context=context,
            constraints=constraints,
            criteria=criteria,
            type=type,
            priority=priority or TASK_PRIORITIES[2],
            group_code=group_bare,
            parent_code=parent_bare,
            deadline_at=deadline_at,
            # Авторство называет поверхность, а не вызывающий: значение из аргумента было бы
            # словом на веру, и отличить заведённое агентом от заведённого человеком стало бы
            # нечем — а бэклог, наполовину придуманный моделью, нечем и отфильтровать.
            created_by=ACTOR_AGENT,
        )
        return AgentTaskCreated(
            workspace=active.code, workspace_title=active.title, code=row.code
        )

    @mcp.tool()
    async def task_update(
        task_code: str,
        title: str | None = None,
        description: str | None = None,
        context: str | None = None,
        constraints: str | None = None,
        criteria: str | None = None,
        type: str | None = None,
        priority: str | None = None,
        group_code: str | None = None,
        deadline_at: datetime | None = None,
    ) -> AgentTaskRow:
        """Update a task — only the fields you pass; anything you omit keeps its value.

        Use it to refile a task under another group, to re-rank it, to raise its type when a
        one-liner turns out to need a plan, or to fill in a brief on a task you created.

        Two things are not here. The plan is text — body_set and its neighbours own it. Status
        moves through task_status, which also stamps when the work started.

        The brief of a task a PERSON set — its title, goal, context, constraints and criteria —
        is theirs, and this refuses to change it. If it is thin, wrong or contradicts itself,
        say so where it will be read: note_add(type="decision") with the question, and carry on
        with what is unambiguous.

        Args:
            task_code: The task to change — a TASK@ code.
            group_code: A GROUP@ code, or an empty string to take it out of its group.
            type: simple / standard / extended — raising it to extended is how a task that
                turned out to need steps gets them.
            priority: burning / high / normal / low / frozen.
            deadline_at: `YYYY-MM-DD HH:MM:SS` in UTC.
        """
        bare = _task_code(task_code)
        await require_scope(TASK_CODE_PREFIX, bare)
        existing = await task_crud.task_get(bare)
        if existing is None:
            raise ValueError(f"Task {task_code} does not exist (or is deleted).")
        brief = {
            "title": title,
            "description": description,
            "context": context,
            "constraints": constraints,
            "criteria": criteria,
        }
        touched = [field for field, value in brief.items() if value is not None]
        if touched and existing.created_by != ACTOR_AGENT:
            raise ValueError(
                f"Task {task_code} was set by a person, and its brief is theirs: "
                f"{', '.join(touched)} cannot be changed from here. A requirement you may "
                "rewrite stops being a requirement. If the brief is thin, wrong or "
                "contradictory, raise it with note_add(type='decision') and go on with what is "
                "unambiguous."
            )
        group_bare = bare_code(group_code, GROUP_CODE_PREFIX)
        if group_bare:
            await require_scope(GROUP_CODE_PREFIX, group_bare)
        row = await task_crud.task_update(
            bare,
            title=title,
            description=description,
            context=context,
            constraints=constraints,
            criteria=criteria,
            type=type,
            priority=priority,
            group_code="" if group_code == "" else group_bare,
            deadline_at=deadline_at if deadline_at is not None else task_crud.KEEP,
        )
        if row is None:
            raise ValueError(f"Task {task_code} does not exist (or is deleted).")
        return (await _rows([row]))[0]

    @mcp.tool()
    async def task_status(task_code: str, status: str) -> AgentTaskStatus:
        """Move a task through its lifecycle — and stamp when that happened.

        backlog → planned → in_progress → in_test → in_review. Hand the work over at in_review
        and stop there: whether it is accepted is the requester's call, and `done` is theirs to
        set. So is `canceled` — deciding that work will not happen is not a decision made from
        inside it.

        The answer says what is still open on this task. Clear it before handing over, not
        after: an unresolved decision is an assumption nobody has checked, and an unresolved
        remark is a request you have not answered. A finding is different — it is about work
        outside this task, and only a person closes it.

        Args:
            task_code: The task to move — a TASK@ code.
            status: backlog / planned / in_progress / in_test / in_review.
        """
        bare = _task_code(task_code)
        active = await require_scope(TASK_CODE_PREFIX, bare)
        if status in (STATUS_DONE, STATUS_CANCELED):
            raise ValueError(
                f"{status!r} is the requester's to set, not yours. Hand the work over with "
                "'in_review' and say what you did; accepting it — or calling it off — is their "
                "decision."
            )
        _checked(status, AGENT_STATUSES, "status")
        row = await task_crud.task_update_status(bare, status)
        if row is None:
            raise ValueError(f"Task {task_code} does not exist (or is deleted).")
        stages = await stage_crud.stage_list_by_task(bare)
        open_notes = await note_crud.note_open_count_by_task_codes([bare])
        blocking = await note_crud.note_open_count_by_task_codes(
            [bare], types=NOTE_TYPES_BLOCKING
        )
        return AgentTaskStatus(
            workspace=active.code,
            workspace_title=active.title,
            code=row.code,
            status=row.status,
            open_notes=open_notes.get(bare, 0),
            blocking_notes=blocking.get(bare, 0),
            unfinished_stages=sum(
                1 for stage in stages if stage.status not in TASK_STATUSES_TERMINAL
            ),
        )


__all__ = ["AGENT_STATUSES", "LIST_CAP", "STATUS_ANY", "STATUS_UNFINISHED", "register"]
