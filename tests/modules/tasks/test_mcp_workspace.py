"""workbench MCP: выбор пространства и забор вокруг него.

Проверяется поведение, ради которого сервер и устроен так: пространство называется один раз,
дальше его никто не передаёт, а промах мимо контура отвечает громко и по имени. Тестов про
«сессии не видят друг друга» здесь нет — in-memory клиент к этому слеп, см.
``test_mcp_session_http.py``.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastmcp.exceptions import ToolError

from src.modules.tasks import TasksModule
from src.modules.tasks.crud import group as group_crud
from src.modules.tasks.crud import task as task_crud
from src.modules.workspace.crud.workspace import workspace_create
from src.modules.workspace.mcp.errors import NO_ACTIVE_WORKSPACE, WORKSPACE_MISMATCH

pytestmark = pytest.mark.db


@pytest.fixture
def counters(config):
    """Счётчики содержимого объявляет ``configure()`` при сборке приложения — зовём его сами.

    Реестр процессный и записи в нём перезаписываются по ключу, поэтому чистить за собой не
    нужно: состояние после фикстуры ровно такое же, как после обычного подъёма приложения.
    """
    TasksModule().configure(FastAPI(), config)


async def test_list_marks_nothing_active_before_a_choice(call, workspace):
    """До выбора активного нет ни одного: пометка — единственный способ это увидеть."""
    rows = await call("workspaces_list")

    assert [row["active"] for row in rows["result"]] == [False]


async def test_list_carries_what_is_inside(call, workspace, counters):
    """Счётчики отвечают на «в каком из них работа» без открывания каждого."""
    await group_crud.group_create(workspace_code=workspace.code, title="Биллинг")
    await task_crud.task_create(workspace_code=workspace.code, title="Счета")

    rows = await call("workspaces_list")

    assert rows["result"][0]["counters"] == {"groups": 1, "tasks": 1}


async def test_use_binds_and_the_list_then_shows_it(call, workspace):
    bound = await call("workspace_use", workspace_code=f"WORKSPACE@{workspace.code}")

    assert bound["active"] is True
    assert bound["code"] == f"WORKSPACE@{workspace.code}"
    rows = await call("workspaces_list")
    assert [row["active"] for row in rows["result"]] == [True]


async def test_use_tells_how_long_the_choice_lasts(call, workspace):
    """Срок жизни привязки агент ниоткуда не выведет — его сообщает ответ, а не описание."""
    bound = await call("workspace_use", workspace_code=workspace.code)

    assert "MCP_WORKSPACE" in bound["note"]
    assert f"WORKSPACE@{workspace.code}" in bound["note"]


async def test_use_refuses_a_workspace_that_is_not_there(call, db):
    with pytest.raises(ToolError, match="does not exist"):
        await call("workspace_use", workspace_code="WORKSPACE@" + "0" * 10)


async def test_bound_tool_refuses_before_a_workspace_is_chosen(call, workspace):
    """Отказ называет ОБА инструмента: без второго агент пойдёт искать несуществующий аргумент."""
    with pytest.raises(ToolError) as caught:
        await call("groups_list")

    assert "workspaces_list" in str(caught.value)
    assert "workspace_use" in str(caught.value)


async def test_bound_tool_takes_no_workspace_argument(mcp):
    """Аргумента нет в СХЕМЕ, а не только в реализации: иначе модель его придумает."""
    tools = {tool.name: tool for tool in await mcp.list_tools()}

    assert "workspace" not in str(tools["groups_list"].inputSchema.get("properties", {}))


async def test_groups_come_from_the_bound_workspace_only(call, workspace):
    other = await workspace_create(title="Личное")
    await group_crud.group_create(workspace_code=workspace.code, title="Биллинг")
    await group_crud.group_create(workspace_code=other.code, title="Ремонт")
    await call("workspace_use", workspace_code=workspace.code)

    answer = await call("groups_list")

    assert [group["title"] for group in answer["groups"]] == ["Биллинг"]


async def test_every_bound_answer_names_its_workspace(call, workspace):
    """Четвёртый рычаг: работу не в том контуре иначе не отличить от пустого результата."""
    await call("workspace_use", workspace_code=workspace.code)

    answer = await call("groups_list")

    assert answer["workspace"] == f"WORKSPACE@{workspace.code}"
    assert answer["workspace_title"] == "Работа"


async def test_a_code_from_another_workspace_is_refused_by_name(call, workspace):
    other = await workspace_create(title="Личное")
    stranger = await task_crud.task_create(workspace_code=other.code, title="Ремонт")
    await call("workspace_use", workspace_code=workspace.code)

    with pytest.raises(ToolError) as caught:
        await call("task_get", task_code=f"TASK@{stranger.code}")

    # Названия обоих, а не только коды: коды случайны и на глаз не читаются.
    assert "'Личное'" in str(caught.value) and "'Работа'" in str(caught.value)


async def test_a_task_of_the_bound_workspace_reads_fine(call, workspace):
    task = await task_crud.task_create(
        workspace_code=workspace.code, title="Счета", description="Чтобы выставлялись"
    )
    await call("workspace_use", workspace_code=workspace.code)

    row = await call("task_get", task_code=f"TASK@{task.code}")

    assert row["title"] == "Счета" and row["description"] == "Чтобы выставлялись"


async def test_no_agent_dto_leaks_its_prose_into_the_schema(mcp):
    """Докстринг агентского DTO уезжает в схему тула и оплачивается при каждом подключении.

    Поэтому пояснения к агентским контрактам живут комментарием НАД классом, а не докстрингом.
    Правило легко нарушить обратно — класс с докстрингом выглядит аккуратнее, — и заметить это
    можно только здесь: ни один функциональный тест от лишнего описания не покраснеет.
    """
    for tool in await mcp.list_tools():
        schema = tool.outputSchema or {}
        assert "description" not in schema, f"{tool.name}: DTO ответа несёт докстринг"
        for name, nested in (schema.get("$defs") or {}).items():
            assert "description" not in nested, f"{tool.name}/{name}: вложенный DTO несёт докстринг"


async def test_refusals_carry_their_rule_code():
    """Коды правил — контракт с интерфейсом и тестами; фраза может меняться, код нет."""
    assert NO_ACTIVE_WORKSPACE == "no_active_workspace"
    assert WORKSPACE_MISMATCH == "workspace_mismatch"
