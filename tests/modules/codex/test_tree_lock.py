"""On PostgreSQL a structural change of a codex tree waits for the tree lock.

SQLite serialises writers by ``BEGIN IMMEDIATE`` alone; PostgreSQL runs two write transactions
side by side, so two crossing moves — each valid on its own — could close a loop. The service
takes one transaction-level advisory lock for the tree; here another connection holds it, and a
create has to wait until it is released. The control — the same create with the lock free — goes
straight through, so a timeout means the lock, not a slow database.
"""

from __future__ import annotations

import asyncio

import pytest
from sqlalchemy import text

from src.core.config import Config
from src.core.database import close_database, get_engine, init_database
from src.modules.codex.crud.codex import codex_create
from src.modules.codex.crud.note import _TREE_LOCK_KEY, note_create

pytestmark = pytest.mark.heavy


@pytest.fixture
async def pg_schema(config: Config):
    engine = await init_database(config)
    from src.core.database.runtime import Base
    import src.modules.codex.models  # noqa: F401
    import src.modules.workspace.models  # noqa: F401

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    try:
        yield
    finally:
        await close_database()


async def test_a_structural_write_waits_for_the_tree_lock(pg_schema):
    python = await codex_create(slug="python", title="Python")
    await asyncio.wait_for(
        note_create(parent_code=python.code, slug="free", title="Без блокировки"), timeout=5
    )

    async with get_engine().connect() as holder:
        await holder.begin()
        await holder.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": _TREE_LOCK_KEY})

        waiting = asyncio.create_task(
            note_create(parent_code=python.code, slug="held", title="Под блокировкой")
        )
        await asyncio.sleep(1)
        assert not waiting.done()

        await holder.rollback()

    created = await asyncio.wait_for(waiting, timeout=5)
    assert created.slug == "held"
