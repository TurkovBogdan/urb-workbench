"""HTTP-API модуля ``tasks``: запись у групп — создание, правка и оба удаления.

Чтение групп живёт в ``test_api_tasks.py`` (там оно стоит рядом со списком задач, который
группами разложен). Здесь — то, что появилось вместе с их разделом: счётчик задач в строке
списка, отказ править удалённое и разная судьба задач у двух удалений.

Приложение с роутером поднимает общая фикстура ``client`` (``conftest.py``).
"""

from __future__ import annotations

import pytest

from src.modules.tasks.constants import CODE_LEN, SORT_DEFAULT
from src.modules.tasks.crud import group as group_crud
from src.modules.tasks.crud import task as task_crud
from src.modules.workspace.crud import workspace as workspace_crud

pytestmark = pytest.mark.db

GROUPS = "/internal/workbench/groups"


async def _workspace(title: str = "Работа"):
    return await workspace_crud.workspace_create(title=title)


# ── счётчик ───────────────────────────────────────────────────────────────────


async def test_list_counts_only_live_tasks_of_the_group(client):
    """Счётчик говорит про то, что человек внутри найдёт: удалённая задача в него не входит."""
    workspace = await _workspace()
    group = await group_crud.group_create(workspace_code=workspace.code, title="Биллинг")
    await task_crud.task_create(
        workspace_code=workspace.code, group_code=group.code, title="Счёт"
    )
    gone = await task_crud.task_create(
        workspace_code=workspace.code, group_code=group.code, title="Отменённая"
    )
    await task_crud.task_delete(gone.code)

    body = (await client.get(GROUPS, params={"workspace": workspace.code})).json()

    assert body[0]["task_count"] == 1


async def test_list_counts_zero_for_an_empty_group(client):
    workspace = await _workspace()
    await group_crud.group_create(workspace_code=workspace.code, title="Пустая")

    body = (await client.get(GROUPS, params={"workspace": workspace.code})).json()

    assert body[0]["task_count"] == 0


# ── создание ──────────────────────────────────────────────────────────────────


async def test_create_puts_the_group_in_the_asked_workspace(client):
    workspace = await _workspace()

    response = await client.post(
        GROUPS, params={"workspace": workspace.code}, json={"title": "Биллинг"}
    )

    assert response.status_code == 201
    assert response.json()["workspace_code"] == f"WORKSPACE@{workspace.code}"
    assert response.json()["sort"] == SORT_DEFAULT


async def test_create_in_a_missing_workspace_is_404(client):
    response = await client.post(
        GROUPS, params={"workspace": "0" * CODE_LEN}, json={"title": "Биллинг"}
    )

    assert response.status_code == 404


async def test_create_rejects_an_unknown_field(client):
    """Опечатка в имени поля — отказ, а не тихо проигнорированное значение (``extra=forbid``)."""
    workspace = await _workspace()

    response = await client.post(
        GROUPS,
        params={"workspace": workspace.code},
        json={"title": "Биллинг", "workspace_code": workspace.code},
    )

    assert response.status_code == 422


# ── правка ────────────────────────────────────────────────────────────────────


async def test_update_replaces_the_whole_card(client):
    """Правка — полная замена: не переданное поле стирается, а не остаётся прежним."""
    workspace = await _workspace()
    group = await group_crud.group_create(
        workspace_code=workspace.code, title="Биллинг", description="Старое", icon="flask"
    )

    body = (
        await client.put(f"{GROUPS}/{group.code}", json={"title": "Оплаты", "sort": 700})
    ).json()

    assert (body["title"], body["description"], body["icon"], body["sort"]) == (
        "Оплаты",
        "",
        "",
        700,
    )


async def test_update_of_a_deleted_group_is_409(client):
    """Удалённое не правится — сначала восстановление; 409, а не 404: зона на экране есть."""
    workspace = await _workspace()
    group = await group_crud.group_create(workspace_code=workspace.code, title="Биллинг")
    await group_crud.group_delete(group.code)

    response = await client.put(f"{GROUPS}/{group.code}", json={"title": "Оплаты"})

    assert response.status_code == 409


async def test_update_wont_move_the_group_between_workspaces(client):
    """Пространства в теле правки нет вовсе: перенос зоны утащил бы за собой все её задачи."""
    workspace = await _workspace()
    stranger = await _workspace("Личное")
    group = await group_crud.group_create(workspace_code=workspace.code, title="Биллинг")

    response = await client.put(
        f"{GROUPS}/{group.code}", json={"title": "Биллинг", "workspace": stranger.code}
    )

    assert response.status_code == 422


# ── удаление ──────────────────────────────────────────────────────────────────


async def test_soft_delete_keeps_the_tasks_in_the_group(client):
    """Мягкое удаление обратимо без следа: задачи держат ссылку, и ``restore`` вернёт раскладку."""
    workspace = await _workspace()
    group = await group_crud.group_create(workspace_code=workspace.code, title="Биллинг")
    task = await task_crud.task_create(
        workspace_code=workspace.code, group_code=group.code, title="Счёт"
    )

    assert (await client.delete(f"{GROUPS}/{group.code}")).status_code == 204

    assert (await task_crud.task_get(task.code)).group_code == group.code


async def test_restore_brings_the_group_back(client):
    workspace = await _workspace()
    group = await group_crud.group_create(workspace_code=workspace.code, title="Биллинг")
    await group_crud.group_delete(group.code)

    body = (await client.post(f"{GROUPS}/{group.code}/restore")).json()

    assert body["deleted_at"] is None


async def test_restore_of_a_live_group_is_409(client):
    """Живую восстанавливать нечего: молчаливое «ок» скрыло бы промах по строке."""
    workspace = await _workspace()
    group = await group_crud.group_create(workspace_code=workspace.code, title="Биллинг")

    response = await client.post(f"{GROUPS}/{group.code}/restore")

    assert response.status_code == 409


async def test_purge_drops_the_group_and_unsorts_its_tasks(client):
    """Снос зоны — не снос работы: задача переживает её и уходит в «Без зоны» (FK SET NULL)."""
    workspace = await _workspace()
    group = await group_crud.group_create(workspace_code=workspace.code, title="Биллинг")
    task = await task_crud.task_create(
        workspace_code=workspace.code, group_code=group.code, title="Счёт"
    )

    assert (await client.delete(f"{GROUPS}/{group.code}/purge")).status_code == 204

    assert await group_crud.group_get(group.code, include_deleted=True) is None
    assert (await task_crud.task_get(task.code)).group_code is None


async def test_purge_of_a_missing_group_is_404(client):
    response = await client.delete(f"{GROUPS}/{'0' * CODE_LEN}/purge")

    assert response.status_code == 404
