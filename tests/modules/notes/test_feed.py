"""The change feed over the live notes CRUD: an open document page learns of every write.

The entity is declared exactly as in production (``notes.module.CHANGE_ENTITIES``). Soft delete
and restore are writes to the row like any other and arrive as ``updated``; only a hard delete is
``deleted``.
"""

from __future__ import annotations

import asyncio
import json

import pytest

from src.core.config import Config
from src.core.database import close_database, init_database
from src.modules.core_changes.bus import bus
from src.modules.core_changes.capture import install
from src.modules.core_changes.entities import clear_entities, register_entity
from src.modules.notes.crud import note as note_crud
from src.modules.notes.module import CHANGE_ENTITIES

pytestmark = pytest.mark.db


@pytest.fixture
async def db(config: Config):
    engine = await init_database(config)
    from src.core.database.runtime import Base
    import src.modules.notes.models  # noqa: F401 — the notes table

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    clear_entities()
    for entity in CHANGE_ENTITIES:
        register_entity(entity)
    install()
    try:
        yield
    finally:
        clear_entities()
        await close_database()


@pytest.fixture
async def feed(db):
    async with bus.subscribe() as queue:

        async def drain() -> list[tuple[str, str, list[str]]]:
            await asyncio.sleep(0)
            out = []
            while not queue.empty():
                for change in json.loads(queue.get_nowait().data)["changes"]:
                    out.append((change["entity"], change["event"], change["ids"]))
            return out

        yield drain


async def test_every_write_reaches_the_feed_under_the_prefixed_code(feed):
    row = await note_crud.note_create(title="Схема")
    code = f"NOTE@{row.code}"
    assert await feed() == [("notes.note", "created", [code])]

    await note_crud.note_update(row.code, body="текст")
    await note_crud.note_delete(row.code)
    await note_crud.note_restore(row.code)
    assert await feed() == [("notes.note", "updated", [code])] * 3

    await note_crud.note_delete(row.code, hard=True)
    assert await feed() == [("notes.note", "deleted", [code])]
