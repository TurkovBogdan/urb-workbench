"""Фикстуры тестов ``tasks``: свежая in-memory БД со схемой модуля, пространство и HTTP-клиент.

``db`` строит схему из ОРМ-моделей (``create_all``) на новой ``:memory:``-базе — миграции сюда
не катятся, их место в heavy-ярусе. Модели ``workspace`` импортируются рядом с нашими: у зоны и
задачи FK на ``workspaces``, и без цели в метаданных ``create_all`` падает
``NoReferencedTableError`` — полный прогон это прячет (чужой модуль свои модели уже подтянул), а
прогон одного модуля ловит сразу.

``workspace`` избавляет почти каждый db-тест от одной и той же первой строки: зона и задача без
пространства не заводятся вовсе. Строку заводит CRUD соседнего модуля — своей ручки у нас больше
нет, и подменять её прямой вставкой значило бы проверять не тот путь, которым ходит приложение.

``app``/``client`` поднимают роутер модуля на голом ``FastAPI``, а не через ``create_app``: тесты
про маршруты модуля, и тащить ради них жизненный цикл приложения незачем. Единственное, что
приходится довесить руками, — ``register_exception_handlers``: без него ``ApiError`` пролетает
мимо обработчика, и вместо 404 с телом ``{"error": …}`` тест получил бы исключение
(см. ``docs/platform/api-zones.md``). Живут здесь, а не в одном файле тестов: поверхностей у
модуля теперь три (пространства, зоны, задачи), и вторая копия подъёма приложения разъехалась бы
с первой на первом же изменении.

``mcp``/``call`` — вторая поверхность модуля, MCP-сервер ``workbench``, поднятый in-memory:
инструменты зовутся ровно так, как их видит агент (``@``-префиксы в кодах, DTO, ошибки
``ToolError``). У этого клиента нет HTTP-запроса, поэтому сессия у всех вызовов теста одна —
общий локальный ключ (``workspace/mcp/session.py``). Это и удобно (привязка держится между
вызовами одного теста), и ограничение: что заголовок сессии вообще доезжает и что две сессии
не видят друг друга, in-memory проверить нельзя — это делает ``test_mcp_session_http.py``.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastmcp import Client
from fastmcp.server.middleware import Middleware
from httpx import ASGITransport, AsyncClient

from src.core.api import register_exception_handlers
from src.core.config import Config
from src.core.database import close_database, init_database
from src.core.mcp.context import McpServerContext
from src.modules.tasks.api import router
from src.modules.tasks.mcp import mcp_server
from src.modules.workspace.crud.workspace import workspace_create


@pytest.fixture
async def db(config: Config):
    engine = await init_database(config)
    from src.core.database.runtime import Base
    import src.modules.tasks.models  # noqa: F401 — регистрирует таблицы tasks
    import src.modules.workspace.models  # noqa: F401 — цель FK ``workspace_code``

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    try:
        yield
    finally:
        await close_database()


@pytest.fixture
async def workspace(db):
    """Живое пространство — корень, от которого отсчитывается всё остальное."""
    return await workspace_create(title="Работа")


@pytest.fixture
async def app(config: Config):
    engine = await init_database(config)
    from src.core.database.runtime import Base
    import src.modules.tasks.models  # noqa: F401 — регистрирует таблицы tasks
    import src.modules.workspace.models  # noqa: F401 — цель FK ``workspace_code``

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    fastapi_app = FastAPI()
    register_exception_handlers(fastapi_app)
    # Префикс повторяет боевой (``TasksModule.internal_router_prefix``): он ``/workbench``, а не
    # ``/tasks``, потому что корень ``/internal/tasks`` занят расписанием ``core_monitoring``.
    fastapi_app.include_router(router, prefix="/internal/workbench")
    try:
        yield fastapi_app
    finally:
        await close_database()


@pytest.fixture
async def client(app):
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as c:
        yield c


@pytest.fixture
async def mcp(db):
    """MCP-сервер ``workbench`` in-memory: auth выключён, audit — no-op."""
    server = mcp_server(McpServerContext(auth=None, audit=Middleware(), allowed_hosts=[]))
    async with Client(server) as c:
        yield c


@pytest.fixture
def call(mcp):
    """Позвать тул и вернуть ``structured_content``. Отказ правила → ``ToolError``."""

    async def _call(name: str, **args):
        return (await mcp.call_tool(name, args)).structured_content

    return _call
