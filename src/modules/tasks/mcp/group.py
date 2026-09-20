"""MCP-тулы раскладки: группы активного пространства и то, что в них лежит.

**Раскладку решает человек, записывает агент.** Правка групп сюда отдана не потому, что тема
перестала быть его делом, а потому, что без неё он не может выполнить произнесённое вслух
«заведи тему под биллинг и перекинь туда вот эти три». Опасность при этом никуда не делась, она
переехала: раньше её держало отсутствие инструмента, теперь держат описания — они говорят
заводить группу по просьбе, а не потому, что бэклог показался агенту неопрятным.

Четыре тула на три сценария: посмотреть раскладку, поправить её, разложить по ней работу.
``tasks_regroup`` живёт здесь, а не среди тулов задачи, по ответу: он меняет не карточку, а
раскладку, и отвечает ею же.

Чтения одной группы по-прежнему нет — ``groups_list`` несёт ровно те же поля, и ``group_get``
отличался бы от него только тем, что возвращает одну строку вместо трёх.

**Оформления (цвет, иконка) в аргументах нет.** ``AgentGroupRow`` их намеренно не несёт: агенту
они не говорят ничего и стоили бы двух полей в каждой строке ответа. Дай их писать — получится
единственное на поверхности поле вслепую, которое он не может прочитать обратно и не может
проверить: палитры в бэкенде нет вовсе, она живёт во фронте. Внешний вид группы выбирает человек.

Позиция задаётся соседом (``place_after`` / ``place_before``), а не числом ``sort``: число —
внутренняя механика списка, и попасть в него агенту нечем.
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

if TYPE_CHECKING:  # fork fastmcp — только backend (через mcp_server(ctx))
    from fastmcp import FastMCP

# Потолок пачки в ``tasks_regroup``. Стоит здесь, а не аргументом: у чтения предел показан
# числами ``shown``/``total``, а у записи такого приёма нет — предел приходится назвать отказом.
# Число выбрано по тому же соображению, что и ``LIST_CAP``: пачка крупнее — это уже не «разложи
# вот эти», а перестройка раскладки, и её человек делает у себя на экране.
REGROUP_CAP = 50


def _group_code(value: str) -> str:
    return bare_code(value, GROUP_CODE_PREFIX) or ""


async def _layout(active: Workspace) -> AgentGroupList:
    """Раскладка пространства со счётчиками — общий ответ всех тулов этого файла."""
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
    """Отказ, если название уже занято живой группой пространства (регистр не считается).

    Уникального индекса на паре «пространство + название» в схеме нет, и без этой проверки в
    одной раскладке заводятся «Биллинг» и «биллинг» — та же грабля, из-за которой из связи
    задач убрали свободное название кучки.
    """
    taken = await group_crud.group_find_by_title(active.code, title)
    if taken is not None and taken.code != own:
        raise ValueError(
            f"{tagged(GROUP_CODE_PREFIX, taken.code)} is already called {taken.title!r} in "
            f"{active.title!r}. File the work there instead of making a second one, or pick a "
            "name that says how this theme differs."
        )


async def _anchor(after: str | None, before: str | None, *, moving: str = "") -> str | None:
    """Точка отсчёта позиции, проверенная ДО первой записи; ``None`` — место не задано.

    Проверка стоит здесь, а не внутри ``group_reorder``, по одной причине: перестановка — ВТОРОЕ
    действие тула, после заведения или правки карточки. Отказ на ней оставлял бы позади
    применённую половину, про которую агенту сказано «не вышло»: он читает отказ как «ничего не
    произошло» и заводит группу заново. Это ровно тот режим, против которого вся поверхность и
    построена, поэтому всё, на чём перестановка способна отказать, выясняется раньше записи.

    Свои проверки у ``group_reorder`` при этом остаются: CRUD зовут и мимо этого тула.
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
    """Переставить группу к уже проверенной точке отсчёта."""
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
            place_after: A GROUP@ code to put this one directly below. Omit to add at the end.
            place_before: A GROUP@ code to put this one directly above.
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
            group_code: The group to change — a GROUP@ code from groups_list.
            title: The theme, short.
            description: Where the boundary runs: what belongs here, and what goes elsewhere.
            place_after: A GROUP@ code to move this one directly below.
            place_before: A GROUP@ code to move this one directly above.
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
        PART OF. Regrouping an epic leaves its subtasks exactly where they were — pass them too
        if that is what you meant.

        Args:
            group_code: A GROUP@ code from groups_list, or an empty string to take these tasks
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
