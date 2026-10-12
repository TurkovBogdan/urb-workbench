"""Fixtures for the ``codex`` tests: a fresh in-memory DB with the module schema and a workspace.

``db`` builds the schema from the ORM models (``create_all``) — migrations are the subject of
``test_migration_codex.py``. Only ``codex`` and ``workspace`` models are registered: a level-2
module that depends on ``workspace`` alone must stand up without any other module's table, and a
single-module run is what catches a stray FK target.

``workspace`` is created through its own module's CRUD — the path the application takes.

``client`` mounts the module router on a bare ``FastAPI`` with the exception handlers, at the
production prefix — without the handlers ``ApiError`` would fly past as an exception instead of a
404. That the router is actually mounted in the assembled zone is ``test_api.py``'s own check.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from src.core.api import register_exception_handlers
from src.core.config import Config
from src.core.database import close_database, init_database
from src.modules.codex.api import router
from src.modules.workspace.crud.workspace import workspace_create


@pytest.fixture
async def db(config: Config):
    engine = await init_database(config)
    from src.core.database.runtime import Base
    import src.modules.codex.models  # noqa: F401 — registers the codex tables
    import src.modules.workspace.models  # noqa: F401 — the ``workspace_code`` FK target

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    try:
        yield
    finally:
        await close_database()


@pytest.fixture
async def workspace(db):
    return await workspace_create(title="Работа")


@pytest.fixture
async def client(db):
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(router, prefix="/internal/codex")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
