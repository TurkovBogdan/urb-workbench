"""The change feed over codex note files: ``codex.file`` names the file and refers to its note."""

from __future__ import annotations

import asyncio
import json

import pytest

from src.core.config import Config
from src.core.database import close_database, init_database
from src.modules.codex import files as codex_files
from src.modules.codex.crud import codex as codex_crud
from src.modules.codex.crud import note as note_crud
from src.modules.codex.module import CHANGE_ENTITIES
from src.modules.core_changes.bus import bus
from src.modules.core_changes.capture import install
from src.modules.core_changes.entities import clear_entities, register_entity
from tests.modules.codex.file_support import codex_file_attach_bytes

pytestmark = pytest.mark.db


@pytest.fixture
async def feed(config: Config, storage):
    engine = await init_database(config)
    from src.core.database.runtime import Base
    import src.modules.codex.models  # noqa: F401 — the codex tables, the storage's with them
    import src.modules.workspace.models  # noqa: F401 — target of the mount's ``workspace_code`` FK

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    clear_entities()
    for entity in CHANGE_ENTITIES:
        register_entity(entity)
    install()
    try:
        async with bus.subscribe() as queue:

            async def drain() -> list[dict]:
                await asyncio.sleep(0)
                out: list[dict] = []
                while not queue.empty():
                    out.extend(json.loads(queue.get_nowait().data)["changes"])
                return [change for change in out if change["entity"] == "codex.file"]

            yield drain
    finally:
        clear_entities()
        await close_database()


async def test_a_file_s_binding_lifecycle_refers_to_its_note(feed):
    codex = await codex_crud.codex_create(segment="python", title="Python")
    note = await note_crud.note_create(parent_code=codex.code, segment="test", title="Тесты")
    await feed()

    bound = await codex_file_attach_bytes(note.code, b"x", filename="x.md")
    created = await feed()
    await codex_files.codex_file_detach(note.code, bound.file_code)
    deleted = await feed()

    file_id = f"FILE@{bound.file_code}"
    assert [(c["event"], c["ids"], c["refs"]) for c in created] == [
        ("created", [file_id], [f"CODEX@{note.code}"])
    ]
    assert [(c["event"], c["ids"], c["refs"]) for c in deleted] == [
        ("deleted", [file_id], [f"CODEX@{note.code}"])
    ]
