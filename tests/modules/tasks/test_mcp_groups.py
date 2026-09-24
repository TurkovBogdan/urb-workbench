"""workbench MCP: раскладка — заведение и правка групп, перенос работы между ними.

Проверяется то, ради чего тулы и появились: агент раскладывает список под управлением человека,
а границы, которые при этом остаются за человеком, держатся отказом, а не просьбой в описании.

Забор пространства здесь не перепроверяется по каждому тулу — он общий и покрыт
``test_mcp_scope.py``; сюда берутся только те его срабатывания, которые у пачки выглядят иначе,
чем у одиночного вызова.
"""

from __future__ import annotations

import pytest
from fastmcp.exceptions import ToolError

from src.modules.tasks.crud import group as group_crud
from src.modules.tasks.crud import task as task_crud
from src.modules.tasks.mcp.group import REGROUP_CAP
from src.modules.workspace.crud.workspace import workspace_create

pytestmark = pytest.mark.db


@pytest.fixture
async def bound(call, workspace):
    """Сессия, уже привязанная к пространству: без этого любой тул отвечает «выбери»."""
    await call("workspace_use", workspace_code=workspace.code)
    return workspace


def _titles(answer) -> list[str]:
    return [row["title"] for row in answer["groups"]]


# ── заведение ─────────────────────────────────────────────────────────────────


async def test_create_answers_with_the_whole_layout(call, bound):
    """Ответ — раскладка, а не расписка: счётчики и порядок сдвинула та же правка."""
    answer = await call("group_create", title="Биллинг", description="Тарифы и счета")

    assert _titles(answer) == ["Биллинг"]
    assert answer["workspace"] == f"WORKSPACE@{bound.code}"
    assert answer["groups"][0]["task_count"] == 0


async def test_create_refuses_a_name_already_taken(call, bound):
    """Две группы с одним названием делят одну работу пополам — отказ называет держателя."""
    await call("group_create", title="Биллинг", description="Тарифы")

    with pytest.raises(ToolError, match="already called"):
        await call("group_create", title="Биллинг", description="Ещё раз")


async def test_create_ignores_case_when_it_checks_the_name(call, bound):
    """Кириллица и регистр: свёртка в Python, потому что SQLite складывает только ASCII."""
    await call("group_create", title="Биллинг", description="Тарифы")

    with pytest.raises(ToolError, match="already called"):
        await call("group_create", title="биллинг", description="Ещё раз")


async def test_create_refuses_an_empty_title(call, bound):
    with pytest.raises(ToolError, match="needs a title"):
        await call("group_create", title="   ", description="Тарифы")


async def test_create_adds_at_the_end_by_default(call, bound):
    await call("group_create", title="Биллинг", description="Тарифы")
    answer = await call("group_create", title="Инфра", description="Железо")

    assert _titles(answer) == ["Биллинг", "Инфра"]


async def test_create_places_relative_to_a_neighbour(call, bound):
    first = await call("group_create", title="Биллинг", description="Тарифы")
    anchor = first["groups"][0]["code"]

    answer = await call(
        "group_create", title="Инфра", description="Железо", place_before=anchor
    )

    assert _titles(answer) == ["Инфра", "Биллинг"]


# ── отказ на позиции не должен оставлять следов ───────────────────────────────
# Найдено прогоном по живому серверу: перестановка — ВТОРОЕ действие тула, и пока она
# проверялась после записи, «не вышло» приходило агенту уже с заведённой группой. Он читает
# отказ как «ничего не произошло» и заводит её заново.


async def test_create_writes_nothing_when_the_anchor_is_not_there(call, bound):
    with pytest.raises(ToolError, match="not a live group"):
        await call(
            "group_create",
            title="Биллинг",
            description="Тарифы",
            place_after="GROUP@" + "0" * 10,
        )

    assert _titles(await call("groups_list")) == []


async def test_create_writes_nothing_when_both_anchors_are_given(call, bound):
    existing = await group_crud.group_create(workspace_code=bound.code, title="Инфра")

    with pytest.raises(ToolError, match="exactly one"):
        await call(
            "group_create",
            title="Биллинг",
            description="Тарифы",
            place_after=f"GROUP@{existing.code}",
            place_before=f"GROUP@{existing.code}",
        )

    assert _titles(await call("groups_list")) == ["Инфра"]


async def test_create_writes_nothing_when_the_anchor_is_of_the_wrong_type(call, bound):
    with pytest.raises(ToolError, match="GROUP@ code is expected"):
        await call(
            "group_create",
            title="Биллинг",
            description="Тарифы",
            place_after="TASK@" + "0" * 10,
        )

    assert _titles(await call("groups_list")) == []


async def test_update_changes_nothing_when_the_anchor_is_not_there(call, bound):
    """У правки половина применённого тише: имя уехало, позиция нет, а ответ — отказ."""
    group = await group_crud.group_create(workspace_code=bound.code, title="Биллинг")

    with pytest.raises(ToolError, match="not a live group"):
        await call(
            "group_update",
            group_code=f"GROUP@{group.code}",
            title="Оплаты",
            place_after="GROUP@" + "0" * 10,
        )

    assert _titles(await call("groups_list")) == ["Биллинг"]


async def test_update_refuses_the_group_as_its_own_anchor(call, bound):
    group = await group_crud.group_create(workspace_code=bound.code, title="Биллинг")

    with pytest.raises(ToolError, match="relative to itself"):
        await call(
            "group_update",
            group_code=f"GROUP@{group.code}",
            title="Оплаты",
            place_before=f"GROUP@{group.code}",
        )

    assert _titles(await call("groups_list")) == ["Биллинг"]


# ── правка ────────────────────────────────────────────────────────────────────


async def test_update_renames_without_moving_the_work(call, bound):
    group = await group_crud.group_create(workspace_code=bound.code, title="Биллинг")
    task = await task_crud.task_create(
        workspace_code=bound.code, title="Счета", group_code=group.code
    )

    answer = await call("group_update", group_code=f"GROUP@{group.code}", title="Оплаты")

    assert _titles(answer) == ["Оплаты"]
    assert (await task_crud.task_get(task.code)).group_code == group.code


async def test_update_may_keep_its_own_name(call, bound):
    """Проверка занятости не должна ловить саму правящуюся группу."""
    group = await group_crud.group_create(workspace_code=bound.code, title="Биллинг")

    answer = await call(
        "group_update",
        group_code=f"GROUP@{group.code}",
        title="Биллинг",
        description="Границы переписаны",
    )

    assert answer["groups"][0]["description"] == "Границы переписаны"


async def test_update_refuses_a_group_in_the_bin(call, bound):
    """Поднять её может только человек — иначе агент заведёт второй «Биллинг» рядом."""
    group = await group_crud.group_create(workspace_code=bound.code, title="Биллинг")
    await group_crud.group_delete(group.code)

    with pytest.raises(ToolError, match="in the bin"):
        await call("group_update", group_code=f"GROUP@{group.code}", title="Оплаты")


async def test_update_moves_the_group_under_its_anchor(call, bound):
    top = await group_crud.group_create(workspace_code=bound.code, title="Биллинг")
    await group_crud.group_create(workspace_code=bound.code, title="Интерфейс")
    last = await group_crud.group_create(workspace_code=bound.code, title="Инфра")

    answer = await call(
        "group_update", group_code=f"GROUP@{last.code}", place_after=f"GROUP@{top.code}"
    )

    assert _titles(answer) == ["Биллинг", "Инфра", "Интерфейс"]


# ── перенос работы ────────────────────────────────────────────────────────────


async def test_regroup_files_a_batch_in_one_call(call, bound):
    group = await group_crud.group_create(workspace_code=bound.code, title="Биллинг")
    first = await task_crud.task_create(workspace_code=bound.code, title="Счета")
    second = await task_crud.task_create(workspace_code=bound.code, title="Тарифы")

    answer = await call(
        "tasks_regroup",
        group_code=f"GROUP@{group.code}",
        task_codes=[f"TASK@{first.code}", f"TASK@{second.code}"],
    )

    assert answer["moved"] == 2
    assert answer["groups"][0]["task_count"] == 2


async def test_regroup_with_an_empty_group_unfiles(call, bound):
    group = await group_crud.group_create(workspace_code=bound.code, title="Биллинг")
    task = await task_crud.task_create(
        workspace_code=bound.code, title="Счета", group_code=group.code
    )

    answer = await call("tasks_regroup", group_code="", task_codes=[f"TASK@{task.code}"])

    assert answer["moved"] == 1
    assert answer["groups"][0]["task_count"] == 0
    assert (await task_crud.task_get(task.code)).group_code is None


async def test_regroup_refuses_the_whole_batch_and_names_every_fault(call, bound):
    """Частично переложенная пачка выглядит как переложенная — поэтому «или все, или никто»."""
    other = await workspace_create(title="Личное")
    group = await group_crud.group_create(workspace_code=bound.code, title="Биллинг")
    mine = await task_crud.task_create(workspace_code=bound.code, title="Счета")
    stranger = await task_crud.task_create(workspace_code=other.code, title="Ремонт")
    missing = "TASK@" + "0" * 10

    with pytest.raises(ToolError) as refusal:
        await call(
            "tasks_regroup",
            group_code=f"GROUP@{group.code}",
            task_codes=[f"TASK@{mine.code}", f"TASK@{stranger.code}", missing],
        )

    message = str(refusal.value)
    assert "another workspace" in message and "not a live task" in message
    assert (await task_crud.task_get(mine.code)).group_code is None


async def test_regroup_refuses_an_empty_batch(call, bound):
    group = await group_crud.group_create(workspace_code=bound.code, title="Биллинг")

    with pytest.raises(ToolError, match="at least one"):
        await call("tasks_regroup", group_code=f"GROUP@{group.code}", task_codes=[])


async def test_regroup_refuses_a_batch_past_the_cap(call, bound):
    """У чтения потолок показан числами, у записи его приходится называть отказом."""
    group = await group_crud.group_create(workspace_code=bound.code, title="Биллинг")

    with pytest.raises(ToolError, match=str(REGROUP_CAP)):
        await call(
            "tasks_regroup",
            group_code=f"GROUP@{group.code}",
            task_codes=[f"TASK@{'0' * 10}"] * (REGROUP_CAP + 1),
        )


async def test_regroup_takes_the_subtasks_along(call, bound):
    """Подзадача — часть эпика и лежит в его группе: переложенный эпик уводит её за собой."""
    group = await group_crud.group_create(workspace_code=bound.code, title="Биллинг")
    epic = await task_crud.task_create(workspace_code=bound.code, title="Тарификация")
    child = await task_crud.task_create(
        workspace_code=bound.code, title="Миграция", parent_code=epic.code
    )

    await call(
        "tasks_regroup", group_code=f"GROUP@{group.code}", task_codes=[f"TASK@{epic.code}"]
    )

    assert (await task_crud.task_get(child.code)).group_code == group.code


async def test_regroup_refuses_a_subtask_named_without_its_parent(call, bound):
    """Подзадачу в чужую группу не кладут — и пачка не ложится ни одной строкой."""
    group = await group_crud.group_create(workspace_code=bound.code, title="Биллинг")
    epic = await task_crud.task_create(workspace_code=bound.code, title="Тарификация")
    child = await task_crud.task_create(
        workspace_code=bound.code, title="Миграция", parent_code=epic.code
    )
    loose = await task_crud.task_create(workspace_code=bound.code, title="Отдельная")

    with pytest.raises(ToolError, match=f"'{child.code}' \\(a subtask of '{epic.code}'\\)"):
        await call(
            "tasks_regroup",
            group_code=f"GROUP@{group.code}",
            task_codes=[f"TASK@{loose.code}", f"TASK@{child.code}"],
        )

    assert (await task_crud.task_get(loose.code)).group_code is None
    assert (await task_crud.task_get(child.code)).group_code is None


async def test_regroup_takes_a_subtask_that_travels_with_its_parent(call, bound):
    group = await group_crud.group_create(workspace_code=bound.code, title="Биллинг")
    epic = await task_crud.task_create(workspace_code=bound.code, title="Тарификация")
    child = await task_crud.task_create(
        workspace_code=bound.code, title="Миграция", parent_code=epic.code
    )

    await call(
        "tasks_regroup",
        group_code=f"GROUP@{group.code}",
        task_codes=[f"TASK@{child.code}", f"TASK@{epic.code}"],
    )

    assert (await task_crud.task_get(epic.code)).group_code == group.code
    assert (await task_crud.task_get(child.code)).group_code == group.code


async def test_regroup_refuses_a_code_of_the_wrong_type(call, bound):
    """Перепутанный аргумент — это не «не найдено», и отказ называет оба типа."""
    group = await group_crud.group_create(workspace_code=bound.code, title="Биллинг")

    with pytest.raises(ToolError, match="TASK@ code is expected"):
        await call(
            "tasks_regroup",
            group_code=f"GROUP@{group.code}",
            task_codes=[f"GROUP@{group.code}"],
        )


# ── границы, которые остались у человека ──────────────────────────────────────


async def test_delete_still_refuses_a_group_and_names_what_to_do(call, bound):
    group = await group_crud.group_create(workspace_code=bound.code, title="Биллинг")

    with pytest.raises(ToolError, match="tasks_regroup"):
        await call("delete", code=f"GROUP@{group.code}")
