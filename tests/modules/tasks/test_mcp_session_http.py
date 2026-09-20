"""workbench MCP поверх РЕАЛЬНО смонтированного сервера: доезжает ли заголовок сессии.

Тест, ради которого вся конструкция и затевалась. In-memory клиент к этому слеп: у него нет
HTTP-запроса, а значит нет и заголовков, и все вызовы делят один локальный ключ. Здесь сервер
поднят так же, как в приложении (``mount_mcp_servers`` → ASGI-подприложение на ``/mcp/workbench``,
``stateless_http``), и клиент ходит к нему через ASGI-транспорт со своими заголовками — ровно то,
что делает шим.

Проверяем три вещи, которых больше негде проверить: заголовок доезжает и привязка по нему
держится; **две сессии не видят выбор друг друга**; пространство из конфига запуска работает
умолчанием, а выбор сессии его перекрывает.
"""

from __future__ import annotations

import asyncio
from contextlib import AsyncExitStack

import pytest
from fastapi import FastAPI
from fastmcp import Client
from fastmcp.client.transports import StreamableHttpTransport
from httpx import ASGITransport, AsyncClient

from src.core.config import Config
from src.core.database import close_database, init_database
from src.core.mcp_headers import MCP_SESSION_HEADER, MCP_WORKSPACE_HEADER
from src.core.module import Module
from src.core.router.mcp import mount_mcp_servers
from src.modules.tasks import TasksModule
from src.modules.tasks.crud import group as group_crud
from src.modules.workspace.crud.workspace import workspace_create

pytestmark = pytest.mark.db

_URL = "http://test/mcp/workbench/"


class _Principal:
    """Утиный принципал: верификатору нужны только ``id`` и ``group``."""

    id = 0
    group = "test"


class _AuthModule(Module):
    """Поставщик единственного ``mcp_token_resolver``: без него монтаж отказывает.

    В приложении эту роль пока держит ``research`` (заглушка до auth-модуля), но тащить сюда
    чужой модуль со всеми его таблицами значило бы проверять его сборку, а не наш заголовок.
    Пускаем всех: тест про заголовок сессии, а не про bearer — за него отвечает
    ``tests/core/test_mcp_server_auth.py``.
    """

    name = "test_auth"

    @staticmethod
    async def resolve(token: str, scope: str):
        return _Principal()

    mcp_token_resolver = staticmethod(resolve)


@pytest.fixture
async def mounted(config: Config):
    """FastAPI со смонтированным ``workbench`` и поднятыми lifespan-ами подприложений.

    Lifespan обязателен: без него session manager форка не инициализирован, и любой вызов
    отвечает 500. В приложении в них входит ``create_app``, здесь — отдельная задача.

    Задача, а не ``async with`` прямо в фикстуре: внутри lifespan-а форка живёт anyio-scope, а
    он требует, чтобы вход и выход случились в ОДНОЙ задаче. Финализацию async-генераторной
    фикстуры pytest выполняет в другой, и выход падал бы «exit cancel scope in a different
    task» — на зелёных тестах, что хуже красных.
    """
    engine = await init_database(config)
    from src.core.database.runtime import Base
    import src.modules.tasks.models  # noqa: F401 — регистрирует таблицы tasks
    import src.modules.workspace.models  # noqa: F401 — цель FK ``workspace_code``

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    app = FastAPI()
    lifespans = mount_mcp_servers(app, [_AuthModule(), TasksModule()], config)
    up, down = asyncio.Event(), asyncio.Event()

    async def hold() -> None:
        async with AsyncExitStack() as stack:
            for lifespan in lifespans:
                await stack.enter_async_context(lifespan)
            up.set()
            await down.wait()

    holder = asyncio.create_task(hold())
    await up.wait()
    try:
        yield app
    finally:
        down.set()
        await holder
        await close_database()


def _session(app: FastAPI, **headers: str) -> Client:
    """Клиент с собственными заголовками — так же, как их ставит шим на свой транспорт.

    ``auth`` обязателен: без ``Authorization`` форк отвечает 401 до инструментов, не спрашивая
    резолвер. Шим передаёт сюда ``MCP_TOKEN``, наша заглушка пускает любой.
    """

    def factory(**kwargs):
        kwargs.pop("timeout", None)
        return AsyncClient(transport=ASGITransport(app=app), base_url="http://test", **kwargs)

    return Client(
        StreamableHttpTransport(
            _URL, headers=headers, auth="test-token", httpx_client_factory=factory
        )
    )


async def _titles(client: Client) -> list[str]:
    answer = await client.call_tool("groups_list", {})
    return [group["title"] for group in answer.structured_content["groups"]]


async def test_the_session_header_carries_the_binding_across_calls(mounted):
    """Привязка ставится одним вызовом и живёт в следующем — хотя сессий у сервера нет."""
    work = await workspace_create(title="Работа")
    await group_crud.group_create(workspace_code=work.code, title="Биллинг")

    async with _session(mounted, **{MCP_SESSION_HEADER: "session-one"}) as client:
        await client.call_tool("workspace_use", {"workspace_code": work.code})
        assert await _titles(client) == ["Биллинг"]


async def test_two_sessions_do_not_see_each_others_choice(mounted):
    """То, ради чего заголовок и заведён: соседнее подключение не двигает твоё пространство."""
    work = await workspace_create(title="Работа")
    home = await workspace_create(title="Личное")
    await group_crud.group_create(workspace_code=work.code, title="Биллинг")
    await group_crud.group_create(workspace_code=home.code, title="Ремонт")

    async with _session(mounted, **{MCP_SESSION_HEADER: "session-one"}) as one:
        await one.call_tool("workspace_use", {"workspace_code": work.code})
        async with _session(mounted, **{MCP_SESSION_HEADER: "session-two"}) as two:
            await two.call_tool("workspace_use", {"workspace_code": home.code})
            assert await _titles(two) == ["Ремонт"]
        # Первая сессия узнаёт о выборе второй только тем, что ничего не изменилось.
        assert await _titles(one) == ["Биллинг"]


async def test_the_configured_workspace_binds_a_fresh_session(mounted):
    """Подключение, настроенное на пространство, работает без единого вызова выбора."""
    work = await workspace_create(title="Работа")
    await group_crud.group_create(workspace_code=work.code, title="Биллинг")

    headers = {MCP_SESSION_HEADER: "fresh", MCP_WORKSPACE_HEADER: f"WORKSPACE@{work.code}"}
    async with _session(mounted, **headers) as client:
        assert await _titles(client) == ["Биллинг"]


async def test_the_session_choice_overrides_the_configured_default(mounted):
    """Умолчание — это умолчание: выбор агента сильнее и в файл настроек не лезет."""
    work = await workspace_create(title="Работа")
    home = await workspace_create(title="Личное")
    await group_crud.group_create(workspace_code=home.code, title="Ремонт")

    headers = {MCP_SESSION_HEADER: "override", MCP_WORKSPACE_HEADER: work.code}
    async with _session(mounted, **headers) as client:
        await client.call_tool("workspace_use", {"workspace_code": home.code})
        assert await _titles(client) == ["Ремонт"]


async def test_a_garbled_configured_workspace_does_not_break_the_server(mounted):
    """Опечатка в НЕобязательной настройке не должна ронять сервер — она даёт обычный отказ."""
    await workspace_create(title="Работа")

    headers = {MCP_SESSION_HEADER: "garbled", MCP_WORKSPACE_HEADER: "GROUP@0000000000"}
    async with _session(mounted, **headers) as client:
        answer = await client.call_tool("workspaces_list", {})
        assert [row["active"] for row in answer.structured_content["result"]] == [False]
