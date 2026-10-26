"""The change feed over task files: ``tasks.file`` names the file and says whose it is.

Declared exactly as in production (``tasks.module.CHANGE_ENTITIES``). A binding row deleted with
its holder goes through the ORM, so its event carries the task, the note and the stage like any
other — a screen recognises "this is about me" without re-reading everything.
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
from src.modules.tasks.constants import TYPE_EXTENDED
from src.modules.tasks.crud import file as file_crud
from src.modules.tasks.crud.stage import stage_create, stage_delete
from src.modules.tasks.crud.task import task_create
from src.modules.tasks.files import FilePlace
from src.modules.tasks.module import CHANGE_ENTITIES
from src.modules.workspace.crud.workspace import workspace_create
from tests.modules.tasks.file_support import task_file_attach_bytes

pytestmark = pytest.mark.db


@pytest.fixture
async def feed(config: Config, storage):
    engine = await init_database(config)
    from src.core.database.runtime import Base
    import src.modules.tasks.models  # noqa: F401 — the tasks tables, the storage's with them
    import src.modules.workspace.models  # noqa: F401 — target of the ``workspace_code`` FK

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
                return [change for change in out if change["entity"] == "tasks.file"]

            yield drain
    finally:
        clear_entities()
        await close_database()


async def test_a_file_s_binding_lifecycle_refers_to_its_task_and_stage(feed):
    workspace = await workspace_create(title="Работа")
    task = await task_create(workspace_code=workspace.code, title="Выпуск", type=TYPE_EXTENDED)
    stage = await stage_create(task_code=task.code, title="Сборка")
    await feed()

    bound = await task_file_attach_bytes(
        task.code, b"log", filename="run.log", place=FilePlace(stage_code=stage.code)
    )
    created = await feed()
    await file_crud.task_file_update(task.code, bound.file_code, title="Лог")
    updated = await feed()
    await stage_delete(stage.code)
    deleted = await feed()

    file_id = f"FILE@{bound.file_code}"
    assert [(c["event"], c["ids"]) for c in created] == [("created", [file_id])]
    assert set(created[0]["refs"]) == {f"TASK@{task.code}", f"STAGE@{stage.code}"}
    assert [(c["event"], c["ids"]) for c in updated] == [("updated", [file_id])]
    assert [(c["event"], c["ids"]) for c in deleted] == [("deleted", [file_id])]
    assert set(deleted[0]["refs"]) == {f"TASK@{task.code}", f"STAGE@{stage.code}"}
