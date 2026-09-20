"""Фикстуры тестов ``workspace``: свежая in-memory БД со схемой модуля и HTTP-клиент.

``db`` строит схему из ОРМ-моделей (``create_all``) на новой ``:memory:``-базе — миграции сюда
не катятся, их место в heavy-ярусе.

``app``/``client`` поднимают роутер модуля на голом ``FastAPI``, а не через ``create_app``: тесты
про маршруты модуля, и тащить ради них жизненный цикл приложения незачем. Единственное, что
приходится довесить руками, — ``register_exception_handlers``: без него ``ApiError`` пролетает
мимо обработчика, и вместо 404 с телом ``{"error": …}`` тест получил бы исключение
(см. ``docs/platform/api-zones.md``).

``no_counters`` чистит реестр счётчиков: приложение целиком подняло бы сюда чужие счётчики
(``tasks`` регистрирует свои в ``configure()``), а модуль обязан отвечать и в одиночестве —
когда над ним не поднято ни одного модуля вовсе.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from src.core.api import register_exception_handlers
from src.core.config import Config
from src.core.database import close_database, init_database
from src.modules.workspace.api import router
from src.modules.workspace.stats import reset_counters


@pytest.fixture(autouse=True)
def no_counters():
    """Реестр счётчиков пуст на входе и на выходе: он process-global, и след пережил бы тест."""
    reset_counters()
    yield
    reset_counters()


@pytest.fixture
async def db(config: Config):
    engine = await init_database(config)
    from src.core.database.runtime import Base
    import src.modules.workspace.models  # noqa: F401 — регистрирует таблицу workspace

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    try:
        yield
    finally:
        await close_database()


@pytest.fixture
async def app(config: Config):
    engine = await init_database(config)
    from src.core.database.runtime import Base
    import src.modules.workspace.models  # noqa: F401 — регистрирует таблицу workspace

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    fastapi_app = FastAPI()
    register_exception_handlers(fastapi_app)
    # Префикс повторяет боевой (``WorkspaceModule.internal_router_prefix``).
    fastapi_app.include_router(router, prefix="/internal/workspace")
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
