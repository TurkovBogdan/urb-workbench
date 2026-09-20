"""HTTP-API плана: этапы, журнал и то, что деталка задачи отдаёт одним ответом.

Здесь проверяется граница, а не правила: сами правила живут в ``test_stage.py`` и ``test_note.py``.
Ручке важно другое — каким статусом отвечает отказ, едет ли рядом с ним КОД правила (по нему
интерфейс показывает свою формулировку, а не английскую фразу из недр CRUD) и приезжают ли
этапы с журналом внутри карточки задачи.
"""

from __future__ import annotations

import pytest

from src.modules.tasks.constants import (
    NOTE_DECISION,
    NOTE_FACT,
    STATUS_DONE,
    TYPE_EXTENDED,
)
from src.modules.tasks.crud import note as note_crud
from src.modules.tasks.crud import stage as stage_crud
from src.modules.tasks.crud import task as task_crud
from src.modules.tasks.errors import NOTE_ALREADY_RESOLVED, STAGE_EVIDENCE_REQUIRED
from src.modules.workspace.crud import workspace as workspace_crud

pytestmark = pytest.mark.db

TASKS = "/internal/workbench/tasks"
STAGES = "/internal/workbench/stages"
NOTES = "/internal/workbench/notes"


async def _task(title: str = "Перенести тарифы"):
    """Задача с этапами, то есть расширенная: у стандартной план живёт прозой и этапов нет."""
    workspace = await workspace_crud.workspace_create(title="Работа")
    return await task_crud.task_create(
        workspace_code=workspace.code, title=title, type=TYPE_EXTENDED
    )


# ── этапы ─────────────────────────────────────────────────────────────────────


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
    """Удалённая задача не правится нигде — этап к ней не завести, как и всё остальное."""
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
    """Главный шлюз плана: отказ несёт код, по которому интерфейс говорит своими словами."""
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


# ── журнал ────────────────────────────────────────────────────────────────────


async def test_note_create_returns_an_open_entry(client):
    task = await _task()

    response = await client.post(
        f"{TASKS}/{task.code}/notes",
        json={"type": NOTE_DECISION, "title": "Взяли SSE", "body": "поток односторонний"},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["resolution"] == ""
    assert body["code"].startswith("NOTE@")


async def test_note_create_with_an_unknown_type_is_400(client):
    task = await _task()

    response = await client.post(
        f"{TASKS}/{task.code}/notes", json={"type": "мысль", "title": "Что-то"}
    )

    assert response.status_code == 400


async def test_note_list_narrows_to_open_entries(client):
    task = await _task()
    await note_crud.note_create(
        task_code=task.code, type=NOTE_FACT, title="Факт", resolution="записано"
    )
    await note_crud.note_create(task_code=task.code, type=NOTE_DECISION, title="Решение")

    body = (
        await client.get(f"{TASKS}/{task.code}/notes", params={"open_only": True})
    ).json()

    assert [row["title"] for row in body] == ["Решение"]


async def test_resolve_closes_the_entry(client):
    task = await _task()
    note = await note_crud.note_create(
        task_code=task.code, type=NOTE_DECISION, title="Куда девать agent"
    )

    body = (
        await client.post(f"{NOTES}/{note.code}/resolve", json={"resolution": "в standard"})
    ).json()

    assert body["resolution"] == "в standard"


async def test_second_resolve_is_409_with_the_rule_code(client):
    """Журнал дописываемый: повтор — не «неверный запрос», а расхождение состояния."""
    task = await _task()
    note = await note_crud.note_create(
        task_code=task.code, type=NOTE_DECISION, title="Куда девать agent"
    )
    await note_crud.note_resolve(note.code, "в standard")

    response = await client.post(
        f"{NOTES}/{note.code}/resolve", json={"resolution": "нет, в extended"}
    )

    assert response.status_code == 409
    assert response.json()["code"] == NOTE_ALREADY_RESOLVED


async def test_resolve_of_a_missing_entry_is_404(client):
    response = await client.post(f"{NOTES}/0000000000/resolve", json={"resolution": "готово"})

    assert response.status_code == 404


# ── карточка задачи целиком ───────────────────────────────────────────────────


async def test_task_detail_carries_the_brief_the_plan_and_both_lists(client):
    """Деталка — экран работы: постановка, план, этапы и журнал едут одним ответом."""
    task = await _task()
    await task_crud.task_update(
        task.code,
        context="Смотреть src/modules/tasks",
        constraints="- нельзя: трогать workspace",
        criteria="1. Тесты зелёные",
        body="План: сначала модели",
    )
    await stage_crud.stage_create(task_code=task.code, title="Модели")
    await note_crud.note_create(task_code=task.code, type=NOTE_DECISION, title="Решение")

    body = (await client.get(f"{TASKS}/{task.code}")).json()

    assert body["context"] == "Смотреть src/modules/tasks"
    assert body["constraints"] == "- нельзя: трогать workspace"
    assert body["criteria"] == "1. Тесты зелёные"
    assert body["body"] == "План: сначала модели"
    assert [row["title"] for row in body["stages"]] == ["Модели"]
    assert [row["title"] for row in body["notes"]] == ["Решение"]


async def test_task_list_row_carries_neither_stages_nor_journal(client):
    """Строка списка остаётся лёгкой: план целиком открывает деталка, а не выдача списком."""
    task = await _task()
    await stage_crud.stage_create(task_code=task.code, title="Модели")

    row = (
        await client.get(TASKS, params={"workspace": f"WORKSPACE@{task.workspace_code}"})
    ).json()[0]

    assert "stages" not in row
    assert "context" not in row


async def test_overlong_plan_is_refused_by_the_api(client):
    """План отказывает, а не усекается: обрезался бы хвост, где перечислены файлы."""
    task = await _task()

    response = await client.put(
        f"{TASKS}/{task.code}",
        json={
            "title": "Перенести тарифы",
            "description": "",
            "context": "",
            "constraints": "",
            "criteria": "",
            "body": "x" * 8193,
            "type": TYPE_EXTENDED,
            "priority": "normal",
            "group_code": None,
            "deadline_at": None,
        },
    )

    assert response.status_code == 400
