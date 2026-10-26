"""An import writes through the ORM, so the change feed carries its rows to the open screens."""

from __future__ import annotations

import asyncio
import json
import shutil

import pytest

from src.modules.core_changes.bus import bus
from src.modules.core_changes.capture import install
from src.modules.core_changes.entities import clear_entities, register_entity
from src.modules.tasks.module import CHANGE_ENTITIES
from src.modules.tasks.transfer.collect import export_task
from src.modules.workspace.crud.workspace import workspace_create

from .support import run_import

pytestmark = pytest.mark.db


async def test_the_imported_rows_reach_the_feed(rich, tmp_path, other_installation):
    exported = await export_task(rich.root, tmp_path / "a.utsk")
    kept = tmp_path / "kept.utsk"
    shutil.copy(exported.path, kept)
    await other_installation()
    workspace = (await workspace_create(title="Там")).code
    clear_entities()
    for entity in CHANGE_ENTITIES:
        register_entity(entity)
    install()
    try:
        async with bus.subscribe() as queue:
            await run_import(kept, workspace)
            await asyncio.sleep(0)
            changes = []
            while not queue.empty():
                changes.extend(json.loads(queue.get_nowait().data)["changes"])
    finally:
        clear_entities()

    seen = {(change["entity"], code) for change in changes for code in change["ids"]}
    assert ("tasks.task", f"TASK@{rich.root}") in seen
    assert ("tasks.file", f"FILE@{rich.task_file}") in seen
    entities = {change["entity"] for change in changes}
    assert {"tasks.task", "tasks.link", "tasks.stage", "tasks.journal", "tasks.note", "tasks.file"} <= entities
