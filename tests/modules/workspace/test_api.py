"""HTTP-API модуля ``workspace`` (/internal/workspace): пространство целиком — от списка до purge.

Здесь только сама сущность и её счётчики как МЕХАНИЗМ: что происходит с зонами и задачами, когда
пространство удаляют, проверяется в тестах модуля, которому они принадлежат
(``tests/modules/tasks/test_workspace_cascade.py``). Модуль уровня 1 обязан быть проверяем в
одиночестве — без единой таблицы модулей поверх.

Приложение с роутером поднимает общая фикстура ``client`` (``conftest.py``); она же чистит реестр
счётчиков, поэтому по умолчанию список в ответе пуст.
"""

from __future__ import annotations

import pytest

from src.modules.workspace.constants import CODE_LEN, DESCRIPTION_MAX, TITLE_MAX
from src.modules.workspace.crud import workspace as workspace_crud
from src.modules.workspace.stats import WorkspaceCounter, register_counter

pytestmark = pytest.mark.db

BASE = "/internal/workspace"


# ── список ────────────────────────────────────────────────────────────────────


async def test_list_returns_workspaces_ordered_by_title(client):
    await workspace_crud.workspace_create(title="Личное")
    await workspace_crud.workspace_create(title="Автономия")

    body = (await client.get(BASE)).json()

    assert [row["title"] for row in body] == ["Автономия", "Личное"]


async def test_list_tags_the_code_with_its_type(client):
    """Код в выдаче — ссылка с типом: по ``WORKSPACE@`` его отличают от кодов модулей поверх."""
    row = await workspace_crud.workspace_create(title="Работа")

    body = (await client.get(BASE)).json()

    assert body[0]["code"] == f"WORKSPACE@{row.code}"


async def test_list_hides_deleted_without_the_flag(client):
    live = await workspace_crud.workspace_create(title="Живое")
    gone = await workspace_crud.workspace_create(title="Удалённое")
    await workspace_crud.workspace_delete(gone.code)

    body = (await client.get(BASE)).json()

    assert [row["code"] for row in body] == [f"WORKSPACE@{live.code}"]


async def test_list_shows_deleted_with_the_flag(client):
    gone = await workspace_crud.workspace_create(title="Удалённое")
    await workspace_crud.workspace_delete(gone.code)

    body = (await client.get(BASE, params={"include_deleted": True})).json()

    assert [row["title"] for row in body] == ["Удалённое"]
    assert body[0]["deleted_at"] is not None


# ── счётчики содержимого (точка расширения) ───────────────────────────────────


async def test_list_has_no_counters_when_nothing_is_registered(client):
    """Ни одного модуля поверх — законное состояние: карточка едет без чисел, а не с нулями."""
    await workspace_crud.workspace_create(title="Работа")

    body = (await client.get(BASE)).json()

    assert body[0]["counters"] == []


async def test_list_carries_a_registered_counter(client):
    """Счётчик объявляет модуль поверх; список лишь собирает объявленное — вместе с ключом подписи."""
    row = await workspace_crud.workspace_create(title="Работа")

    async def count(codes: list[str]) -> dict[str, int]:
        return {code: 7 for code in codes}

    register_counter(
        WorkspaceCounter(key="notes", label_key="notes.workspace.counter", count_by_codes=count)
    )

    body = (await client.get(BASE)).json()

    assert body[0]["counters"] == [
        {"key": "notes", "label_key": "notes.workspace.counter", "count": 7}
    ]
    assert body[0]["code"] == f"WORKSPACE@{row.code}"


async def test_a_counter_that_skipped_a_workspace_reads_as_zero(client):
    """«Не вернули» и «ничего не нашли» — один ответ для карточки; ноль подставляет сборка."""
    await workspace_crud.workspace_create(title="Пустое")

    async def count(codes: list[str]) -> dict[str, int]:
        return {}

    register_counter(
        WorkspaceCounter(key="notes", label_key="notes.workspace.counter", count_by_codes=count)
    )

    body = (await client.get(BASE)).json()

    assert body[0]["counters"][0]["count"] == 0


async def test_counters_follow_the_declared_order(client):
    """Порядок задаёт регистрация (больший ``sort`` раньше), а не то, кто первым поднялся."""
    await workspace_crud.workspace_create(title="Работа")

    async def count(codes: list[str]) -> dict[str, int]:
        return {code: 1 for code in codes}

    register_counter(
        WorkspaceCounter(key="later", label_key="a", count_by_codes=count, sort=100)
    )
    register_counter(
        WorkspaceCounter(key="earlier", label_key="b", count_by_codes=count, sort=900)
    )

    body = (await client.get(BASE)).json()

    assert [counter["key"] for counter in body[0]["counters"]] == ["earlier", "later"]


# ── создание ──────────────────────────────────────────────────────────────────


async def test_create_returns_201_and_the_card(client):
    response = await client.post(
        BASE,
        json={"title": "Работа", "description": "о работе", "color": "teal", "icon": "folder"},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["title"] == "Работа"
    assert (body["color"], body["icon"]) == ("teal", "folder")
    assert body["deleted_at"] is None
    assert len(body["code"].removeprefix("WORKSPACE@")) == CODE_LEN


async def test_create_rejects_a_blank_title(client):
    """Имя из одних пробелов отвергается наравне с пустым: без имени карточку не найти."""
    response = await client.post(BASE, json={"title": "   "})

    assert response.status_code == 422


async def test_create_rejects_an_overlong_title(client):
    response = await client.post(BASE, json={"title": "я" * (TITLE_MAX + 1)})

    assert response.status_code == 422


async def test_create_rejects_an_overlong_description(client):
    response = await client.post(
        BASE, json={"title": "Работа", "description": "я" * (DESCRIPTION_MAX + 1)}
    )

    assert response.status_code == 422


async def test_create_rejects_an_unknown_field(client):
    """Опечатка в имени поля — отказ, а не тихо проигнорированное значение (``extra=forbid``)."""
    response = await client.post(BASE, json={"title": "Работа", "colour": "teal"})

    assert response.status_code == 422


# ── чтение одного ─────────────────────────────────────────────────────────────


async def test_get_accepts_both_code_forms(client):
    """Префиксный код человек копирует из интерфейса, голый модули отдают друг другу изнутри."""
    row = await workspace_crud.workspace_create(title="Работа")

    bare = await client.get(f"{BASE}/{row.code}")
    tagged = await client.get(f"{BASE}/WORKSPACE@{row.code}")

    assert bare.status_code == tagged.status_code == 200
    assert bare.json() == tagged.json()


async def test_get_returns_a_deleted_workspace_too(client):
    row = await workspace_crud.workspace_create(title="Работа")
    await workspace_crud.workspace_delete(row.code)

    body = (await client.get(f"{BASE}/{row.code}")).json()

    assert body["deleted_at"] is not None


async def test_get_of_a_missing_workspace_is_404(client):
    response = await client.get(f"{BASE}/{'0' * CODE_LEN}")

    assert response.status_code == 404
    assert response.json()["error"]


async def test_a_foreign_code_prefix_is_a_bad_request(client):
    """Код чужого типа — перепутанный аргумент, а не пропавшая запись: 400, а не 404."""
    row = await workspace_crud.workspace_create(title="Работа")

    response = await client.get(f"{BASE}/AREA@{row.code}")

    assert response.status_code == 400


# ── правка ────────────────────────────────────────────────────────────────────


async def test_update_replaces_the_card(client):
    row = await workspace_crud.workspace_create(
        title="Работа", description="о работе", icon="folder", color="teal"
    )

    body = (
        await client.put(
            f"{BASE}/{row.code}",
            json={"title": "Дело", "description": "", "color": "red", "icon": "rocket"},
        )
    ).json()

    assert body["title"] == "Дело"
    assert body["description"] == ""
    assert (body["color"], body["icon"]) == ("red", "rocket")


async def test_update_of_a_deleted_workspace_is_a_conflict(client):
    row = await workspace_crud.workspace_create(title="Работа")
    await workspace_crud.workspace_delete(row.code)

    response = await client.put(f"{BASE}/{row.code}", json={"title": "Дело"})

    assert response.status_code == 409


async def test_update_of_a_missing_workspace_is_404(client):
    response = await client.put(f"{BASE}/{'0' * CODE_LEN}", json={"title": "Дело"})

    assert response.status_code == 404


# ── мягкое удаление и восстановление ──────────────────────────────────────────


async def test_delete_is_soft(client):
    row = await workspace_crud.workspace_create(title="Работа")

    response = await client.delete(f"{BASE}/{row.code}")

    assert response.status_code == 204
    assert (await workspace_crud.workspace_get(row.code)) is None
    assert (await workspace_crud.workspace_get(row.code, include_deleted=True)) is not None


async def test_delete_of_a_missing_workspace_is_404(client):
    response = await client.delete(f"{BASE}/{'0' * CODE_LEN}")

    assert response.status_code == 404


async def test_restore_brings_the_workspace_back_to_the_list(client):
    row = await workspace_crud.workspace_create(title="Работа")
    await client.delete(f"{BASE}/{row.code}")

    restored = await client.post(f"{BASE}/{row.code}/restore")

    assert restored.status_code == 200
    assert restored.json()["deleted_at"] is None
    assert [item["title"] for item in (await client.get(BASE)).json()] == ["Работа"]


async def test_restore_of_a_live_workspace_is_a_conflict(client):
    row = await workspace_crud.workspace_create(title="Работа")

    response = await client.post(f"{BASE}/{row.code}/restore")

    assert response.status_code == 409


async def test_restore_of_a_missing_workspace_is_404(client):
    response = await client.post(f"{BASE}/{'0' * CODE_LEN}/restore")

    assert response.status_code == 404


# ── физическое удаление ───────────────────────────────────────────────────────


async def test_purge_removes_the_row(client):
    row = await workspace_crud.workspace_create(title="Работа")

    response = await client.delete(f"{BASE}/{row.code}/purge")

    assert response.status_code == 204
    assert (await workspace_crud.workspace_get(row.code, include_deleted=True)) is None


async def test_purge_works_on_a_softly_deleted_workspace(client):
    """Обычный путь из интерфейса: сначала в корзину, потом «удалить навсегда»."""
    row = await workspace_crud.workspace_create(title="Работа")
    await client.delete(f"{BASE}/{row.code}")

    response = await client.delete(f"{BASE}/{row.code}/purge")

    assert response.status_code == 204
    assert (await workspace_crud.workspace_get(row.code, include_deleted=True)) is None


async def test_purge_leaves_the_neighbours_alone(client):
    doomed = await workspace_crud.workspace_create(title="Под снос")
    kept = await workspace_crud.workspace_create(title="Остаётся")

    await client.delete(f"{BASE}/{doomed.code}/purge")

    assert (await workspace_crud.workspace_get(kept.code)) is not None


async def test_purge_of_a_missing_workspace_is_404(client):
    response = await client.delete(f"{BASE}/{'0' * CODE_LEN}/purge")

    assert response.status_code == 404
