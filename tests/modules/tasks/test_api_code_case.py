"""HTTP API of ``tasks``: a code in any case finds its row, and every answer is upper case.

The interface builds its URLs from what the API returned, but bookmarks, pasted links and saved
browser state carry codes from before they went upper case. Each kind of place a code arrives —
path segment, query parameter, body field — is exercised here with the lower-case form.
"""

from __future__ import annotations

import re

import pytest

from src.modules.tasks.crud import group as group_crud
from src.modules.tasks.crud import journal as journal_crud
from src.modules.tasks.crud import stage as stage_crud
from src.modules.tasks.crud import task as task_crud

pytestmark = pytest.mark.db

API = "/internal/workbench"
_CODE = re.compile(
    r"\b(?:WORKSPACE|TASKGROUP|GROUP|TASK|STAGE|JOURNAL|NOTE)@[0-9A-Za-z]{10}", re.IGNORECASE
)


def low(prefix: str, bare: str) -> str:
    return f"{prefix}@{bare}".lower()


def _all_upper(payload) -> bool:
    codes = _CODE.findall(str(payload))
    return bool(codes) and all(code == code.upper() for code in codes)


@pytest.fixture
async def world(workspace):
    group = await group_crud.group_create(workspace_code=workspace.code, title="Биллинг")
    task = await task_crud.task_create(
        workspace_code=workspace.code, title="Эпик", group_code=group.code, type="extended"
    )
    stage = await stage_crud.stage_create(task_code=task.code, title="Модели")
    await journal_crud.journal_create(task_code=task.code, type="fact", title="Факт")
    return workspace.code, group.code, task.code, stage.code


@pytest.mark.parametrize(
    "url",
    [
        lambda w, g, t, s: f"{API}/groups?workspace={low('WORKSPACE', w)}",
        lambda w, g, t, s: f"{API}/groups/{low('GROUP', g)}",
        lambda w, g, t, s: f"{API}/tasks?workspace={low('WORKSPACE', w)}&group={low('GROUP', g)}",
        lambda w, g, t, s: f"{API}/tasks/search?workspace={low('WORKSPACE', w)}&query=Факт&in_journal=true",
        lambda w, g, t, s: f"{API}/tasks/{low('TASK', t)}",
        lambda w, g, t, s: f"{API}/tasks/{low('TASK', t)}/stages",
        lambda w, g, t, s: f"{API}/tasks/{low('TASK', t)}/journal",
    ],
    ids=["groups?workspace", "groups/{code}", "tasks?workspace&group", "tasks/search", "tasks/{code}", "stages", "journal"],
)
async def test_reads_take_a_lower_case_code(client, world, url):
    response = await client.get(url(*world))

    assert response.status_code == 200, response.text
    assert _all_upper(response.json()), response.json()


async def test_body_codes_are_folded_on_create(client, world):
    workspace, group, task, _ = world

    response = await client.post(
        f"{API}/tasks",
        json={
            "workspace": low("WORKSPACE", workspace),
            "title": "Подзадача",
            "parent_code": low("TASK", task),
        },
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["parent_code"] == f"TASK@{task}"
    assert body["group_code"] == f"TASKGROUP@{group}"
    assert body["code"] == body["code"].upper()


async def test_a_stage_and_a_journal_entry_take_lower_case_codes_on_write(client, world):
    _, _, task, stage = world

    renamed = await client.put(f"{API}/stages/{low('STAGE', stage)}", json={"title": "Схема"})
    added = await client.post(
        f"{API}/tasks/{low('TASK', task)}/journal",
        json={"type": "decision", "title": "Ещё", "stage_code": low("STAGE", stage)},
    )

    assert renamed.status_code == 200, renamed.text
    assert added.status_code == 201, added.text
    assert added.json()["stage_code"] == f"STAGE@{stage}"
    assert added.json()["code"].startswith("JOURNAL@")


async def test_a_journal_entry_resolves_by_a_lower_case_code(client, world):
    _, _, task, _ = world
    entry = await journal_crud.journal_create(task_code=task, type="decision", title="Решение")

    response = await client.post(
        f"{API}/journal/journal@{entry.code.lower()}/resolve", json={"resolution": "проверено"}
    )

    assert response.status_code == 200, response.text
    assert response.json()["code"] == f"JOURNAL@{entry.code}"
    assert (await journal_crud.journal_get(entry.code)).resolution == "проверено"


@pytest.mark.parametrize("word", ["note", "Note", "NOTE"])
async def test_the_retired_note_word_of_an_entry_is_refused_with_its_code(client, world, word):
    """``NOTE@`` was the journal's code until 2026-10-09 and now names a task note: an entry
    quoted by it is refused with the code it has now, and neither resolved nor deleted."""
    _, _, task, _ = world
    entry = await journal_crud.journal_create(task_code=task, type="decision", title="Решение")
    old = f"{word}@{entry.code.lower()}"

    resolved = await client.post(f"{API}/journal/{old}/resolve", json={"resolution": "проверено"})
    deleted = await client.delete(f"{API}/journal/{old}")

    for response in (resolved, deleted):
        assert response.status_code == 400, response.text
        assert f"its code is JOURNAL@{entry.code}" in response.json()["error"]
    stored = await journal_crud.journal_get(entry.code)
    assert stored is not None and stored.resolution == ""


async def test_a_journal_entry_is_deleted_by_a_lower_case_code(client, world):
    _, _, task, _ = world
    kept = await journal_crud.journal_create(task_code=task, type="fact", title="Остаётся")
    gone = await journal_crud.journal_create(task_code=task, type="fact", title="Уходит")

    response = await client.delete(f"{API}/journal/journal@{gone.code.lower()}")

    assert response.status_code == 204, response.text
    assert await journal_crud.journal_get(gone.code) is None
    assert await journal_crud.journal_get(kept.code) is not None
