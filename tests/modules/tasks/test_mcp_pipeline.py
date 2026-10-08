"""workbench MCP: a complex task from connecting to handing in — as one scenario.

What is checked is not each tool on its own (the neighbouring files do that) but that they add
up to work: find, read, plan, **rework the plan by deleting stages**, execute with evidence,
write to the journal and hand in. Exactly this run exposed half of the fixes in the data layer —
such holes don't show up in a per-tool table.
"""

from __future__ import annotations

import pytest
from fastmcp.exceptions import ToolError

from src.modules.tasks.constants import ACTOR_HUMAN, TYPE_EXTENDED
from src.modules.tasks.crud import task as task_crud

pytestmark = pytest.mark.db


@pytest.fixture
async def brief(workspace):
    """A task set by a HUMAN: the agent may not accept the work on it."""
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

    # ── find the work ─────────────────────────────────────────────────────────
    found = await call("tasks_list", query="тариф")
    assert [row["title"] for row in found["tasks"]] == [brief.title]
    assert found["workspace_title"] == "Работа"

    task = f"TASK@{brief.code}"
    detail = await call("task_get", task_code=task)
    assert detail["criteria"].startswith("1. Тесты биллинга")
    assert detail["stages"] == [] and detail["open_notes"] == []

    # ── plan ──────────────────────────────────────────────────────────────────
    plan = await call(
        "content_set",
        code=task,
        field="plan",
        text="## Подход\nТариф считается в одном месте.\n\n## Файлы\nПрочитано: tariff.py\n",
    )
    assert plan["length"] > 0
    # Appending to the plan returns the seam, not the text: what was sent is not echoed back.
    seam = await call(
        "content_add", code=task, field="plan", text="Меняю: tariff.py\n", position="end"
    )
    assert "<text>" in seam["edit"]
    # A section is replaced whole, and the answer shows the SPAN of the cut, not a tidy joint.
    cut = await call(
        "content_set_section",
        code=task,
        field="plan",
        heading="## Файлы",
        text="## Файлы\nБез изменений\n",
    )
    assert cut["removed_length"] > 0 and cut["stopped_at"] is None
    first = await call("stage_add", task_code=task, title="Схема")
    second = await call("stage_add", task_code=task, title="Пересчёт")
    third = await call("stage_add", task_code=task, title="Миграция")
    fourth = await call("stage_add", task_code=task, title="Лишний")
    assert [s["number"] for s in (first, second, third, fourth)] == [1, 2, 3, 4]

    # ── rework the plan: merge two stages and drop the extra one ──────────────
    # fastmcp wraps a scalar answer in ``{"result": …}``.
    assert (await call("delete", code=second["code"]))["result"] is True
    assert (await call("delete", code=fourth["code"]))["result"] is True

    # A gap in the numbering is legal: the number orders, it does not count.
    after_cut = await call("task_get", task_code=task)
    assert [s["number"] for s in after_cut["stages"]] == [1, 3]

    # A taken number is an ordinary rework mistake, and it deserves a human-readable answer.
    with pytest.raises(ToolError, match="is taken by stage"):
        await call("stage_add", task_code=task, title="Дубль", number=1)

    # A freed one is fine.
    await call("stage_update", stage_code=third["code"], number=2, title="Пересчёт и миграция")
    assert [s["number"] for s in (await call("task_get", task_code=task))["stages"]] == [1, 2]

    # ── execute ───────────────────────────────────────────────────────────────
    await call("content_set", code=first["code"], field="body", text="Развернуть Calculator.")

    started = await call("stage_update", stage_code=first["code"], status="in_progress")
    # Starting a stage does not move the task, and the answer shows that.
    assert started["task_status"] == "backlog"
    await call("task_status", task_code=task, status="in_progress")

    # The course of the work goes to the progress diary, an entry appended at a time.
    await call(
        "content_add",
        code=task,
        field="progress",
        text="- схема развёрнута → пересчёт\n",
        position="end",
    )

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

    # ── a side finding: not about this task, so it must not block hand-in ─────
    await call("note_add", task_code=task, type="finding", title="Рядом мёртвый код")

    await call("stage_close", stage_code=third["code"], evidence="alembic upgrade head → ok")

    # ── hand in ───────────────────────────────────────────────────────────────
    await call(
        "content_set",
        code=task,
        field="result",
        text="Тарифы считаются по новой схеме. Проверено: pytest -q → 12 passed.",
    )
    handed = await call("task_status", task_code=task, status="in_review")
    assert handed["status"] == "in_review"
    assert handed["unfinished_stages"] == 0
    # The finding is visible to the person but does not block hand-in: the executor has no way
    # to close it.
    assert handed["open_notes"] == 1 and handed["blocking_notes"] == 0


async def test_the_agent_corrects_the_brief_of_a_human_task(call, workspace, brief):
    """A ban pushed the agent into workarounds — the brief written to a file, carried over by the
    person by hand; the edit is legitimate."""
    await call("workspace_use", workspace_code=workspace.code)

    await call(
        "task_update",
        task_code=f"TASK@{brief.code}",
        context="Смотреть src/billing/tariff.py и src/billing/invoice.py",
        criteria="1. `pytest tests/billing -q` зелёный",
    )

    stored = await task_crud.task_get(brief.code)
    assert stored.context == "Смотреть src/billing/tariff.py и src/billing/invoice.py"
    assert stored.criteria == "1. `pytest tests/billing -q` зелёный"
    assert stored.title == brief.title and stored.constraints == brief.constraints
    assert stored.created_by == ACTOR_HUMAN


async def test_the_agent_writes_the_brief_of_its_own_subtask(call, workspace, brief):
    """The agent creates a subtask itself and sets its criteria right away."""
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

    with pytest.raises(ToolError, match="A journal entry is not deleted"):
        await call("delete", code=note["code"])

    assert [row["code"] for row in (await call("notes_list", task_code=f"TASK@{brief.code}"))["notes"]] == [
        note["code"]
    ]


async def test_only_the_extended_task_takes_stages(call, workspace):
    """Stages are the only thing that sets an extended task apart from a standard one.

    Both rungs are checked: simple and standard refuse alike, and raising the type is the
    regular path for work that turned out longer than expected.
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
    """Refusing stages is not refusing record-keeping: a standard task has a prose plan and a
    journal."""
    await call("workspace_use", workspace_code=workspace.code)
    task = await call(
        "task_create", title="Поправить форму", description="Комментарий сохраняется",
        type="standard",
    )

    plan = "Меняю форму счёта."
    assert (await call("content_set", code=task["code"], field="plan", text=plan))["length"] == len(
        plan
    )
    note = await call(
        "note_add", task_code=task["code"], type="fact", title="invoice.py:88"
    )
    assert note["code"].startswith("NOTE@")


async def test_a_task_the_agent_creates_is_signed_by_the_surface(call, workspace):
    """Authorship names the surface: there is no argument for it, so nothing to forge it with."""
    await call("workspace_use", workspace_code=workspace.code)
    created = await call("task_create", title="Своя", description="Цель")

    assert (await call("task_get", task_code=created["code"]))["created_by"] == "agent"


async def test_task_get_carries_the_three_work_fields(call, workspace):
    """Plan, progress and result come by their own names; a task has no ``body`` any more."""
    await call("workspace_use", workspace_code=workspace.code)
    row = await task_crud.task_create(
        workspace_code=workspace.code,
        title="Задача",
        plan="## Подход",
        progress="- начато → дальше тесты",
        result="Сделано",
    )

    detail = await call("task_get", task_code=f"TASK@{row.code}")

    assert (detail["plan"], detail["progress"], detail["result"]) == (
        "## Подход",
        "- начато → дальше тесты",
        "Сделано",
    )
    assert "body" not in detail


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
