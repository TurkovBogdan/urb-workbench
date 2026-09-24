"""Метка источника: ``X-Client-Id`` запроса доезжает до сообщения ленты как ``origin``.

Самое хрупкое место — переход границы greenlet'а: обработчики событий сессии SQLAlchemy async
выполняет не в задаче запроса, а в greenlet'е, и переменная контекста обязана туда дойти. Поэтому
проверка идёт через настоящий HTTP-запрос и настоящую запись, а не через подстановку значения.
"""

from __future__ import annotations

import asyncio
import json

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from src.core.api import register_exception_handlers
from src.core.config import Config
from src.core.database import close_database, init_database
from src.modules.core_changes.bus import bus
from src.modules.core_changes.capture import install
from src.modules.core_changes.entities import clear_entities, register_entity
from src.modules.core_changes.origin import OriginMiddleware, current_origin
from src.modules.tasks.api import router
from src.modules.tasks.crud import task as task_crud
from src.modules.tasks.module import CHANGE_ENTITIES
from src.modules.workspace.crud.workspace import workspace_create

pytestmark = pytest.mark.db


@pytest.fixture
async def client(config: Config):
    engine = await init_database(config)
    from src.core.database.runtime import Base
    import src.modules.tasks.models  # noqa: F401
    import src.modules.workspace.models  # noqa: F401

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    clear_entities()
    for entity in CHANGE_ENTITIES:
        register_entity(entity)
    install()
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(router, prefix="/internal/workbench")
    app.add_middleware(OriginMiddleware)
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            yield c
    finally:
        clear_entities()
        await close_database()


async def _messages(queue) -> list[dict]:
    await asyncio.sleep(0)
    out = []
    while not queue.empty():
        out.append(json.loads(queue.get_nowait().data))
    return out


async def test_client_id_header_becomes_origin(client):
    workspace = await workspace_create(title="Работа")
    task = await task_crud.task_create(workspace_code=workspace.code, title="Счёт")
    async with bus.subscribe() as queue:
        response = await client.patch(
            f"/internal/workbench/tasks/{task.code}",
            json={"context": "из вкладки"},
            headers={"X-Client-Id": "tab-42"},
        )
        assert response.status_code == 200
        messages = await _messages(queue)
    assert [m["origin"] for m in messages] == ["tab-42"]
    assert messages[0]["changes"][0]["ids"] == [f"TASK@{task.code}"]


async def test_request_without_header_has_no_origin(client):
    workspace = await workspace_create(title="Работа")
    task = await task_crud.task_create(workspace_code=workspace.code, title="Счёт")
    async with bus.subscribe() as queue:
        await client.patch(f"/internal/workbench/tasks/{task.code}", json={"context": "агент"})
        messages = await _messages(queue)
    assert [m["origin"] for m in messages] == [None]


async def test_origin_does_not_leak_past_the_request(client):
    workspace = await workspace_create(title="Работа")
    task = await task_crud.task_create(workspace_code=workspace.code, title="Счёт")
    await client.patch(
        f"/internal/workbench/tasks/{task.code}", json={"context": "x"}, headers={"X-Client-Id": "tab-1"}
    )
    assert current_origin.get() is None
    async with bus.subscribe() as queue:
        await task_crud.task_update(task.code, context="после запроса")
        messages = await _messages(queue)
    assert [m["origin"] for m in messages] == [None]
