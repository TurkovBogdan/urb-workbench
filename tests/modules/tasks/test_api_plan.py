"""The plan's HTTP API: stages, the journal, and what the task detail returns in one response.

This tests the boundary, not the rules: the rules themselves live in ``test_stage.py`` and
``test_journal.py``. What matters to the endpoint is different — which status a refusal answers
with, whether the rule CODE travels with it (the interface shows its own wording by that code
rather than an English phrase from deep inside the CRUD), and whether stages and the journal
arrive inside the task card.
"""

from __future__ import annotations

import pytest

from src.modules.tasks.constants import (
    JOURNAL_DECISION,
    JOURNAL_FACT,
    STATUS_DONE,
    TYPE_EXTENDED,
)
from src.modules.tasks.crud import journal as journal_crud
from src.modules.tasks.crud import stage as stage_crud
from src.modules.tasks.crud import task as task_crud
from src.modules.tasks.errors import JOURNAL_ALREADY_RESOLVED, STAGE_EVIDENCE_REQUIRED
from src.modules.workspace.crud import workspace as workspace_crud

pytestmark = pytest.mark.db

TASKS = "/internal/workbench/tasks"
STAGES = "/internal/workbench/stages"
JOURNAL = "/internal/workbench/journal"


async def _task(title: str = "Перенести тарифы"):
    """A task with stages, i.e. extended: a standard one keeps its plan as prose, no stages."""
    workspace = await workspace_crud.workspace_create(title="Работа")
    return await task_crud.task_create(
        workspace_code=workspace.code, title=title, type=TYPE_EXTENDED
    )


# ── stages ────────────────────────────────────────────────────────────────────


async def test_stage_list_is_scoped_to_its_task(client):
    task = await _task()
    stranger = await _task("Чужая")
    await stage_crud.stage_create(task_code=task.code, title="Модели")
    await stage_crud.stage_create(task_code=stranger.code, title="Чужой этап")

    body = (await client.get(f"{TASKS}/{task.code}/stages")).json()

    assert [row["title"] for row in body] == ["Модели"]
    assert body[0]["code"].startswith("STAGE@")
    assert body[0]["task_code"] == f"TASK@{task.code}"


async def test_stage_create_returns_the_row_with_its_number(client):
    task = await _task()

    response = await client.post(
        f"{TASKS}/{task.code}/stages", json={"title": "Модели", "description": "о чём"}
    )

    assert response.status_code == 201
    assert response.json()["number"] == 1


async def test_stage_create_on_a_deleted_task_is_409(client):
    """A deleted task is not editable anywhere — no stage can be added to it, like anything else."""
    task = await _task()
    await task_crud.task_delete(task.code)

    response = await client.post(f"{TASKS}/{task.code}/stages", json={"title": "Модели"})

    assert response.status_code == 409


async def test_stage_update_replaces_the_card(client):
    task = await _task()
    stage = await stage_crud.stage_create(task_code=task.code, title="Модели")

    body = (
        await client.put(
            f"{STAGES}/{stage.code}",
            json={
                "title": "Модели и миграции",
                "description": "",
                "body": "",
                "evidence": "pytest -q → 6 passed",
            },
        )
    ).json()

    assert body["title"] == "Модели и миграции"
    assert body["evidence"] == "pytest -q → 6 passed"


async def test_closing_without_evidence_is_400_with_the_rule_code(client):
    """The plan's main gate: the refusal carries a code the interface words in its own terms."""
    task = await _task()
    stage = await stage_crud.stage_create(task_code=task.code, title="Модели")

    response = await client.post(f"{STAGES}/{stage.code}/status", json={"status": STATUS_DONE})

    assert response.status_code == 400
    assert response.json()["code"] == STAGE_EVIDENCE_REQUIRED


async def test_closing_with_evidence_stamps_the_finish(client):
    task = await _task()
    stage = await stage_crud.stage_create(task_code=task.code, title="Модели")
    await stage_crud.stage_update(stage.code, evidence="pytest -q → 6 passed")

    body = (
        await client.post(f"{STAGES}/{stage.code}/status", json={"status": STATUS_DONE})
    ).json()

    assert body["status"] == STATUS_DONE
    assert body["finished_at"] is not None


async def test_stage_status_of_a_missing_stage_is_404(client):
    response = await client.post(f"{STAGES}/0000000000/status", json={"status": STATUS_DONE})

    assert response.status_code == 404


async def test_stage_delete_is_204_then_404(client):
    task = await _task()
    stage = await stage_crud.stage_create(task_code=task.code, title="Модели")

    assert (await client.delete(f"{STAGES}/{stage.code}")).status_code == 204
    assert (await client.delete(f"{STAGES}/{stage.code}")).status_code == 404


async def test_a_foreign_prefix_in_the_stage_segment_is_400(client):
    task = await _task()
    stage = await stage_crud.stage_create(task_code=task.code, title="Модели")

    response = await client.delete(f"{STAGES}/TASK@{stage.code}")

    assert response.status_code == 400


# ── journal ───────────────────────────────────────────────────────────────────


async def test_journal_create_returns_an_open_entry(client):
    task = await _task()

    response = await client.post(
        f"{TASKS}/{task.code}/journal",
        json={"type": JOURNAL_DECISION, "title": "Взяли SSE", "body": "поток односторонний"},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["resolution"] == ""
    assert body["code"].startswith("JOURNAL@")


async def test_journal_create_with_an_unknown_type_is_400(client):
    task = await _task()

    response = await client.post(
        f"{TASKS}/{task.code}/journal", json={"type": "мысль", "title": "Что-то"}
    )

    assert response.status_code == 400


async def test_journal_list_narrows_to_open_entries(client):
    task = await _task()
    await journal_crud.journal_create(
        task_code=task.code, type=JOURNAL_FACT, title="Факт", resolution="записано"
    )
    await journal_crud.journal_create(task_code=task.code, type=JOURNAL_DECISION, title="Решение")

    body = (
        await client.get(f"{TASKS}/{task.code}/journal", params={"open_only": True})
    ).json()

    assert [row["title"] for row in body] == ["Решение"]


async def test_resolve_closes_the_entry(client):
    task = await _task()
    entry = await journal_crud.journal_create(
        task_code=task.code, type=JOURNAL_DECISION, title="Куда девать agent"
    )

    body = (
        await client.post(f"{JOURNAL}/{entry.code}/resolve", json={"resolution": "в standard"})
    ).json()

    assert body["resolution"] == "в standard"


async def test_second_resolve_is_409_with_the_rule_code(client):
    """The journal is append-only: a repeat is not a "bad request" but a state conflict."""
    task = await _task()
    entry = await journal_crud.journal_create(
        task_code=task.code, type=JOURNAL_DECISION, title="Куда девать agent"
    )
    await journal_crud.journal_resolve(entry.code, "в standard")

    response = await client.post(
        f"{JOURNAL}/{entry.code}/resolve", json={"resolution": "нет, в extended"}
    )

    assert response.status_code == 409
    assert response.json()["code"] == JOURNAL_ALREADY_RESOLVED


async def test_resolve_of_a_missing_entry_is_404(client):
    response = await client.post(f"{JOURNAL}/0000000000/resolve", json={"resolution": "готово"})

    assert response.status_code == 404


# ── the whole task card ───────────────────────────────────────────────────────


async def test_task_detail_carries_the_brief_the_plan_and_both_lists(client):
    """The detail is the working screen: brief, plan, stages and journal come in one response."""
    task = await _task()
    await task_crud.task_update(
        task.code,
        context="Смотреть src/modules/tasks",
        constraints="- нельзя: трогать workspace",
        criteria="1. Тесты зелёные",
        plan="План: сначала модели",
        progress="- модели готовы → API",
        result="Модели и API на месте",
    )
    await stage_crud.stage_create(task_code=task.code, title="Модели")
    await journal_crud.journal_create(task_code=task.code, type=JOURNAL_DECISION, title="Решение")

    body = (await client.get(f"{TASKS}/{task.code}")).json()

    assert body["context"] == "Смотреть src/modules/tasks"
    assert body["constraints"] == "- нельзя: трогать workspace"
    assert body["criteria"] == "1. Тесты зелёные"
    assert body["plan"] == "План: сначала модели"
    assert body["progress"] == "- модели готовы → API"
    assert body["result"] == "Модели и API на месте"
    assert "body" not in body
    assert [row["title"] for row in body["stages"]] == ["Модели"]
    assert [row["title"] for row in body["journal"]] == ["Решение"]
    assert "notes" not in body


async def test_task_list_row_carries_neither_stages_nor_journal(client):
    """A list row stays light: the full plan is opened by the detail, not by the list."""
    task = await _task()
    await stage_crud.stage_create(task_code=task.code, title="Модели")

    row = (
        await client.get(TASKS, params={"workspace": f"WORKSPACE@{task.workspace_code}"})
    ).json()[0]

    assert "stages" not in row
    assert "context" not in row


async def test_overlong_plan_is_refused_by_the_api(client):
    """The plan is refused, not truncated: truncation would cut the tail that lists the files."""
    task = await _task()

    response = await client.put(
        f"{TASKS}/{task.code}",
        json={
            "title": "Перенести тарифы",
            "description": "",
            "context": "",
            "constraints": "",
            "criteria": "",
            "plan": "x" * 8193,
            "type": TYPE_EXTENDED,
            "priority": "normal",
            "group_code": None,
            "deadline_at": None,
        },
    )

    assert response.status_code == 400
