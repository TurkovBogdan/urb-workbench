"""workbench MCP: комплексная задача от подключения до сдачи — одним сценарием.

Проверяется не каждый инструмент по отдельности (это делают соседние файлы), а то, что они
складываются в работу: найти, прочитать, спланировать, **переработать план с удалением этапов**,
исполнить с доказательствами, записать в журнал и сдать. Ровно этот прогон вскрыл половину
правок в слое данных — по таблице инструментов такие дыры не видны.
"""

from __future__ import annotations

import pytest
from fastmcp.exceptions import ToolError

from src.modules.tasks.constants import ACTOR_HUMAN, TYPE_EXTENDED
from src.modules.tasks.crud import task as task_crud

pytestmark = pytest.mark.db


@pytest.fixture
async def brief(workspace):
    """Задача, поставленная ЧЕЛОВЕКОМ: её бриф агенту править нельзя."""
    return await task_crud.task_create(
        workspace_code=workspace.code,
        title="Перевести тарифы на новую схему",
        description="Счета выставляются по новой схеме, старые не ломаются",
        context="Смотреть src/billing/tariff.py",
        constraints="Не трогать модуль оплат",
        criteria="1. Тесты биллинга зелёные\n2. Старые счета пересчитываются один в один",
        type=TYPE_EXTENDED,
        created_by=ACTOR_HUMAN,
    )


async def test_the_whole_pipeline_holds_together(call, workspace, brief):
    await call("workspace_use", workspace_code=workspace.code)

    # ── найти работу ──────────────────────────────────────────────────────────
    found = await call("tasks_list", query="тариф")
    assert [row["title"] for row in found["tasks"]] == [brief.title]
    assert found["workspace_title"] == "Работа"

    task = f"TASK@{brief.code}"
    detail = await call("task_get", task_code=task)
    assert detail["criteria"].startswith("1. Тесты биллинга")
    assert detail["stages"] == [] and detail["open_notes"] == []

    # ── спланировать ──────────────────────────────────────────────────────────
    plan = await call(
        "body_set",
        code=task,
        text="## Подход\nТариф считается в одном месте.\n\n## Файлы\nПрочитано: tariff.py\n",
    )
    assert plan["length"] > 0
    # Дописывание в план — шов, а не тело: присланный текст назад не едет.
    seam = await call("body_add", code=task, text="Меняю: tariff.py\n", position="end")
    assert "<text>" in seam["edit"]
    # Раздел заменяется целиком, и ответ показывает РАЗМАХ выреза, а не аккуратный стык.
    cut = await call(
        "body_set_section", code=task, heading="## Файлы", text="## Файлы\nБез изменений\n"
    )
    assert cut["removed_length"] > 0 and cut["stopped_at"] is None
    first = await call("stage_add", task_code=task, title="Схема")
    second = await call("stage_add", task_code=task, title="Пересчёт")
    third = await call("stage_add", task_code=task, title="Миграция")
    fourth = await call("stage_add", task_code=task, title="Лишний")
    assert [s["number"] for s in (first, second, third, fourth)] == [1, 2, 3, 4]

    # ── переработать план: схлопнуть два этапа и выбросить лишний ─────────────
    # Скалярный ответ fastmcp заворачивает в ``{"result": …}``.
    assert (await call("delete", code=second["code"]))["result"] is True
    assert (await call("delete", code=fourth["code"]))["result"] is True

    # Дыра в нумерации легальна: номер упорядочивает, а не считает.
    after_cut = await call("task_get", task_code=task)
    assert [s["number"] for s in after_cut["stages"]] == [1, 3]

    # Занятый номер — обычная ошибка переработки, и отвечать на неё надо по-человечески.
    with pytest.raises(ToolError, match="is taken by stage"):
        await call("stage_add", task_code=task, title="Дубль", number=1)

    # Освободившийся — можно.
    await call("stage_update", stage_code=third["code"], number=2, title="Пересчёт и миграция")
    assert [s["number"] for s in (await call("task_get", task_code=task))["stages"]] == [1, 2]

    # ── исполнить ─────────────────────────────────────────────────────────────
    # Не начатый этап переписывается свободно.
    await call("body_set", code=first["code"], text="Развернуть Calculator.")

    started = await call("stage_update", stage_code=first["code"], status="in_progress")
    # Старт этапа задачу не двигает, и ответ это показывает.
    assert started["task_status"] == "backlog"
    await call("task_status", task_code=task, status="in_progress")

    # А начатый — нет: позади план застывший, иначе «обещали одно, сделали другое» исчезает.
    with pytest.raises(ToolError, match="does not get rewritten"):
        await call("body_set", code=first["code"], text="Ну, что вышло, то и планировали")

    decision = await call(
        "note_add", task_code=task, type="decision",
        title="Пересчёт делаем на лету", stage_code=first["code"],
    )
    await call("note_resolve", note_code=decision["code"], resolution="pytest -q → 12 passed")

    with pytest.raises(ToolError, match="evidence is empty"):
        await call("stage_close", stage_code=first["code"], evidence="   ")

    closed = await call(
        "stage_close", stage_code=first["code"], evidence="pytest -q → 12 passed; tariff.py:40-88"
    )
    assert closed["stage"]["status"] == "done"

    # ── попутная находка: она не про эту задачу и сдачу держать не должна ─────
    await call("note_add", task_code=task, type="finding", title="Рядом мёртвый код")

    await call("stage_close", stage_code=third["code"], evidence="alembic upgrade head → ok")

    # ── сдать ─────────────────────────────────────────────────────────────────
    handed = await call("task_status", task_code=task, status="in_review")
    assert handed["status"] == "in_review"
    assert handed["unfinished_stages"] == 0
    # Находка видна человеку, но сдачу не держит: закрыть её исполнителю нечем.
    assert handed["open_notes"] == 1 and handed["blocking_notes"] == 0


async def test_the_brief_of_a_human_task_is_not_the_agents_to_rewrite(call, workspace, brief):
    """Критерий, который исполнитель вправе переписать, перестаёт быть критерием."""
    await call("workspace_use", workspace_code=workspace.code)

    with pytest.raises(ToolError, match="brief is theirs"):
        await call("task_update", task_code=f"TASK@{brief.code}", criteria="1. Как получится")


async def test_the_agent_writes_the_brief_of_its_own_subtask(call, workspace, brief):
    """Своя постановка — своя: запрет про чужую волю, а не про поле."""
    await call("workspace_use", workspace_code=workspace.code)
    child = await call(
        "task_create", title="Подзадача", description="Часть работы",
        parent_code=f"TASK@{brief.code}", type="standard",
    )

    row = await call("task_update", task_code=child["code"], criteria="1. Схема без дрейфа")

    assert row["code"] == child["code"]


async def test_the_agent_cannot_declare_the_work_accepted(call, workspace, brief):
    await call("workspace_use", workspace_code=workspace.code)

    for verdict in ("done", "canceled"):
        with pytest.raises(ToolError, match="requester's to set"):
            await call("task_status", task_code=f"TASK@{brief.code}", status=verdict)


async def test_a_remark_is_not_the_agents_to_write(call, workspace, brief):
    await call("workspace_use", workspace_code=workspace.code)

    with pytest.raises(ToolError, match="requester's word"):
        await call("note_add", task_code=f"TASK@{brief.code}", type="remark", title="Сам себе")


async def test_a_journal_entry_is_never_deleted(call, workspace, brief):
    await call("workspace_use", workspace_code=workspace.code)
    note = await call(
        "note_add", task_code=f"TASK@{brief.code}", type="fact", title="tariff.py:88"
    )

    with pytest.raises(ToolError, match="append-only"):
        await call("delete", code=note["code"])


async def test_only_the_extended_task_takes_stages(call, workspace):
    """Этапы — единственное, чем расширенная отличается от стандартной.

    Проверяются обе ступени: простая и стандартная отказывают одинаково, а повышение типа —
    штатный путь для работы, которая оказалась длиннее, чем думали.
    """
    await call("workspace_use", workspace_code=workspace.code)
    task = await call("task_create", title="Записаться к врачу", description="Запись есть")

    for level in ("simple", "standard"):
        if level != "simple":
            await call("task_update", task_code=task["code"], type=level)
        with pytest.raises(ToolError, match="stages belong to extended only"):
            await call("stage_add", task_code=task["code"], title="Этап")

    await call("task_update", task_code=task["code"], type="extended")
    assert (await call("stage_add", task_code=task["code"], title="Этап"))["number"] == 1


async def test_a_standard_task_still_keeps_a_plan_and_a_journal(call, workspace):
    """Отказ по этапам — не отказ по ведению: план прозой и журнал у стандартной есть."""
    await call("workspace_use", workspace_code=workspace.code)
    task = await call(
        "task_create", title="Поправить форму", description="Комментарий сохраняется",
        type="standard",
    )

    plan = "Меняю форму счёта."
    assert (await call("body_set", code=task["code"], text=plan))["length"] == len(plan)
    note = await call(
        "note_add", task_code=task["code"], type="fact", title="invoice.py:88"
    )
    assert note["code"].startswith("NOTE@")


async def test_a_task_the_agent_creates_is_signed_by_the_surface(call, workspace):
    """Авторство называет поверхность: аргумента нет, и подделать его нечем."""
    await call("workspace_use", workspace_code=workspace.code)
    created = await call("task_create", title="Своя", description="Цель")

    assert (await call("task_get", task_code=created["code"]))["created_by"] == "agent"


async def test_unfinished_is_the_default_and_history_does_not_crowd_it(call, workspace):
    await call("workspace_use", workspace_code=workspace.code)
    live = await call("task_create", title="Живая", description="Цель")
    gone = await task_crud.task_create(
        workspace_code=workspace.code, title="Сделанная", status="done"
    )

    assert [row["code"] for row in (await call("tasks_list"))["tasks"]] == [live["code"]]
    assert {row["title"] for row in (await call("tasks_list", status="any"))["tasks"]} == {
        "Живая",
        "Сделанная",
    }
    assert [row["title"] for row in (await call("tasks_list", status="done"))["tasks"]] == [
        gone.title
    ]
