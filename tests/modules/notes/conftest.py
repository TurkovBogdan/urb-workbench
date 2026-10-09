"""``notes`` test fixtures: a fresh in-memory DB with only this module's table, and an HTTP client.

Only ``notes`` models are registered: a level-1 module must answer on its own, without a single
table of the modules above it. ``app`` mounts the module router on a bare ``FastAPI`` with the
exception handlers — without them ``ApiError`` would fly past as an exception instead of a 404.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from src.core.api import register_exception_handlers
from src.core.config import Config
from src.core.database import close_database, init_database
from src.modules.notes.api import router


async def _schema(config: Config) -> None:
    engine = await init_database(config)
    from src.core.database.runtime import Base
    import src.modules.notes.models  # noqa: F401 — registers the notes table

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


@pytest.fixture
async def db(config: Config):
    await _schema(config)
    try:
        yield
    finally:
        await close_database()


@pytest.fixture
async def client(config: Config):
    await _schema(config)
    app = FastAPI()
    register_exception_handlers(app)
    # The prefix mirrors the production one (``NotesModule.internal_router_prefix``).
    app.include_router(router, prefix="/internal/notes")
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            yield c
    finally:
        await close_database()
