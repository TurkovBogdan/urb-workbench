"""Активное пространство сессии: хранение, умолчание и уборка.

Здесь слой проверяется напрямую, без MCP-клиента: заголовков у прямого вызова нет, и все эти
тесты работают в одной локальной сессии — ровно то поведение, которое обещано для вызова вне
HTTP. Что заголовок доезжает и что сессии не видят друг друга, проверяет
``tests/modules/tasks/test_mcp_session_http.py``.
"""

from __future__ import annotations

from datetime import timedelta

import pytest

from src.core.module_state import module_store
from src.core.utils.date import utc_now
from src.modules.workspace.crud.workspace import workspace_create, workspace_delete
from src.modules.workspace.mcp import session
from src.modules.workspace.mcp.errors import NO_ACTIVE_WORKSPACE, WorkspaceScopeError

pytestmark = pytest.mark.db


async def test_nothing_is_active_until_something_is_chosen(db):
    assert await session.active_code() is None


async def test_a_call_without_http_lands_in_one_named_session(db):
    """Вызов вне HTTP — не ошибка, а другой способ звать; ключ у него один и говорящий."""
    assert session.session_id() == "local"


async def test_the_binding_survives_the_call_that_made_it(db):
    workspace = await workspace_create(title="Работа")

    await session.bind(workspace.code)

    assert await session.active_code() == workspace.code


async def test_rebinding_replaces_rather_than_accumulates(db):
    first = await workspace_create(title="Работа")
    second = await workspace_create(title="Личное")

    await session.bind(first.code)
    await session.bind(second.code)

    assert await session.active_code() == second.code


async def test_require_active_refuses_with_the_rule_code(db):
    with pytest.raises(WorkspaceScopeError) as caught:
        await session.require_active()

    assert caught.value.code == NO_ACTIVE_WORKSPACE


async def test_a_binding_pointing_at_nothing_reads_as_no_choice(db):
    """Пространство могли снести после привязки: это то же «выбери», а не внутренняя ошибка."""
    await session.bind("0000000000")

    with pytest.raises(WorkspaceScopeError):
        await session.require_active()


async def test_work_continues_in_a_workspace_deleted_after_binding(db):
    """Удалённое пространство свои задачи не теряет — обрывать по нему работу было бы враньём."""
    workspace = await workspace_create(title="Работа")
    await session.bind(workspace.code)
    await workspace_delete(workspace.code)

    assert (await session.require_active()).code == workspace.code


async def test_prune_drops_abandoned_bindings_and_keeps_live_ones(db):
    """Уборка нужна, чтобы таблица не росла от каждого запуска клиента, — и только для этого."""
    workspace = await workspace_create(title="Работа")
    await session.bind(workspace.code)
    store = module_store("workspace")
    stale = utc_now() - timedelta(days=90)
    await store.set(
        "mcp_session:long-gone", {"workspace": workspace.code, "at": stale.isoformat()}
    )

    assert await session.prune() == 1
    assert await store.get("mcp_session:long-gone") is None
    assert await session.active_code() == workspace.code
