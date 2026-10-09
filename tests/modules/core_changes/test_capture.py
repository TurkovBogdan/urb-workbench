"""The change feed over the live ``tasks`` CRUD: what reaches a listener after each write.

Entities are declared exactly as in production (``tasks.module.CHANGE_ENTITIES``), and each
declaration is checked by create, update and delete: a forgotten or broken mark is a screen that
stopped refreshing without a single error.
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
from src.modules.notes.module import CHANGE_ENTITIES as NOTES_CHANGE_ENTITIES
from src.modules.tasks.constants import TYPE_EXTENDED
from src.modules.tasks.crud.group import group_create, group_delete, group_update
from src.modules.tasks.crud.link import link_reorder
from src.modules.tasks.crud.journal import journal_create, journal_delete, journal_resolve
from src.modules.tasks.crud.note import task_note_add
from src.modules.tasks.crud.stage import stage_create, stage_delete, stage_update
from src.modules.tasks.crud.task import task_create, task_delete, task_restore, task_update
from src.modules.tasks.module import CHANGE_ENTITIES
from src.modules.workspace.crud.workspace import workspace_create

pytestmark = pytest.mark.db


@pytest.fixture
async def db(config: Config):
    engine = await init_database(config)
    from src.core.database.runtime import Base
    import src.modules.tasks.models  # noqa: F401 — the tasks tables
    import src.modules.workspace.models  # noqa: F401 — target of the ``workspace_code`` FK

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    clear_entities()
    # A task note's document is the ``notes`` module's entity, declared by that module.
    for entity in (*CHANGE_ENTITIES, *NOTES_CHANGE_ENTITIES):
        register_entity(entity)
    install()
    try:
        yield
    finally:
        clear_entities()
        await close_database()


@pytest.fixture
async def workspace(db):
    return await workspace_create(title="Работа")


@pytest.fixture
async def feed(db):
    """Bus listener: ``await feed()`` — everything since the previous call, as a list of changes."""
    async with bus.subscribe() as queue:

        async def drain() -> list[dict]:
            await asyncio.sleep(0)
            out: list[dict] = []
            while not queue.empty():
                message = queue.get_nowait()
                out.extend(json.loads(message.data)["changes"])
            return out

        yield drain


def _find(changes: list[dict], entity: str, event: str) -> dict:
    matches = [c for c in changes if c["entity"] == entity and c["event"] == event]
    assert len(matches) == 1, f"expected one {entity}/{event} in {changes}"
    return matches[0]


async def test_undeclared_writes_publish_nothing(db, feed):
    clear_entities()
    await workspace_create(title="Без объявлений")
    assert await feed() == []


async def test_workspace_itself_is_not_in_the_feed(workspace, feed):
    # The tasks module never declared workspaces — so they're not in the feed, though they change.
    await workspace_create(title="Второе")
    assert await feed() == []


async def test_task_created_carries_its_edge_and_refs(workspace, feed):
    group = await group_create(workspace_code=workspace.code, title="Оплаты")
    await feed()
    task = await task_create(workspace_code=workspace.code, title="Счёт", group_code=group.code)
    changes = await feed()

    created = _find(changes, "tasks.task", "created")
    assert created["ids"] == [f"TASK@{task.code}"]
    assert set(created["refs"]) == {f"WORKSPACE@{workspace.code}", f"TASKGROUP@{group.code}"}
    edge = _find(changes, "tasks.link", "created")
    assert edge["ids"] == [f"TASK@{task.code}"]
    # Something created in the same transaction is not also reported as an update.
    assert not [c for c in changes if c["event"] == "updated" and c["entity"] == "tasks.task"]


async def test_task_update_reports_old_and_new_group(workspace, feed):
    first = await group_create(workspace_code=workspace.code, title="Первая")
    second = await group_create(workspace_code=workspace.code, title="Вторая")
    task = await task_create(workspace_code=workspace.code, title="Счёт", group_code=first.code)
    await feed()

    await task_update(task.code, group_code=second.code)
    updated = _find(await feed(), "tasks.task", "updated")
    assert updated["ids"] == [f"TASK@{task.code}"]
    # A move touches both groups: the task left one and arrived in the other.
    assert {f"TASKGROUP@{first.code}", f"TASKGROUP@{second.code}"} <= set(updated["refs"])


async def test_update_without_real_change_publishes_nothing(workspace, feed):
    task = await task_create(workspace_code=workspace.code, title="Счёт")
    await feed()
    await task_update(task.code, title="Счёт")
    assert [c for c in await feed() if c["entity"] == "tasks.task"] == []


async def test_soft_delete_and_restore_name_the_whole_branch(workspace, feed):
    parent = await task_create(workspace_code=workspace.code, title="Родитель")
    child = await task_create(workspace_code=workspace.code, title="Ребёнок", parent_code=parent.code)
    await feed()

    await task_delete(parent.code)
    deleted = _find(await feed(), "tasks.task", "updated")
    assert set(deleted["ids"]) == {f"TASK@{parent.code}", f"TASK@{child.code}"}

    await task_restore(parent.code)
    restored = _find(await feed(), "tasks.task", "updated")
    assert set(restored["ids"]) == {f"TASK@{parent.code}", f"TASK@{child.code}"}


async def test_hard_delete_names_tasks_and_edges(workspace, feed):
    task = await task_create(workspace_code=workspace.code, title="Черновик")
    await feed()
    await task_delete(task.code, hard=True)
    changes = await feed()
    assert _find(changes, "tasks.task", "deleted")["ids"] == [f"TASK@{task.code}"]
    assert _find(changes, "tasks.link", "deleted")["ids"] == [f"TASK@{task.code}"]


async def test_reorder_reports_the_moved_edges(workspace, feed):
    first = await task_create(workspace_code=workspace.code, title="Первая")
    second = await task_create(workspace_code=workspace.code, title="Вторая")
    await feed()
    await link_reorder(second.code, after_code=None)
    edges = _find(await feed(), "tasks.link", "updated")
    assert f"TASK@{second.code}" in edges["ids"]
    assert set(edges["ids"]) <= {f"TASK@{first.code}", f"TASK@{second.code}"}


async def test_group_lifecycle(workspace, feed):
    group = await group_create(workspace_code=workspace.code, title="Оплаты")
    created = _find(await feed(), "tasks.group", "created")
    assert created["ids"] == [f"TASKGROUP@{group.code}"]
    assert created["refs"] == [f"WORKSPACE@{workspace.code}"]

    await group_update(group.code, title="Деньги")
    assert _find(await feed(), "tasks.group", "updated")["ids"] == [f"TASKGROUP@{group.code}"]

    await group_delete(group.code)
    assert _find(await feed(), "tasks.group", "updated")["ids"] == [f"TASKGROUP@{group.code}"]

    await group_delete(group.code, hard=True)
    assert _find(await feed(), "tasks.group", "deleted")["ids"] == [f"TASKGROUP@{group.code}"]


async def test_stage_lifecycle_refers_to_its_task(workspace, feed):
    task = await task_create(workspace_code=workspace.code, title="Выпуск", type=TYPE_EXTENDED)
    await feed()

    stage = await stage_create(task_code=task.code, title="Сборка")
    created = _find(await feed(), "tasks.stage", "created")
    assert created["ids"] == [f"STAGE@{stage.code}"]
    assert created["refs"] == [f"TASK@{task.code}"]

    await stage_update(stage.code, title="Сборка и тесты")
    assert _find(await feed(), "tasks.stage", "updated")["ids"] == [f"STAGE@{stage.code}"]

    await stage_delete(stage.code)
    assert _find(await feed(), "tasks.stage", "deleted")["ids"] == [f"STAGE@{stage.code}"]


async def test_journal_lifecycle_refers_to_its_task(workspace, feed):
    task = await task_create(workspace_code=workspace.code, title="Выпуск", type=TYPE_EXTENDED)
    await feed()

    entry = await journal_create(task_code=task.code, type="decision", title="Берём SSE")
    created = _find(await feed(), "tasks.journal", "created")
    assert created["ids"] == [f"JOURNAL@{entry.code}"]
    assert created["refs"] == [f"TASK@{task.code}"]

    await journal_resolve(entry.code, "Решено")
    assert _find(await feed(), "tasks.journal", "updated")["ids"] == [f"JOURNAL@{entry.code}"]

    await journal_delete(entry.code)
    assert _find(await feed(), "tasks.journal", "deleted")["ids"] == [f"JOURNAL@{entry.code}"]


async def test_failed_write_publishes_nothing(workspace, feed):
    await feed()
    with pytest.raises(ValueError):
        await task_create(workspace_code=workspace.code, title="Сирота", group_code="нет-такой")
    assert await feed() == []


async def test_content_edits_reach_the_feed_for_every_field(workspace, feed):
    """An agent's content edit is what an open task page must redraw. The handlers write the
    ORM row directly, past CRUD — so the feed sees them only through flush capture, and that is
    pinned here per field rather than assumed."""
    from src.modules.tasks.mcp.content.registry import MCP_CONTENT_HANDLERS

    task = await task_create(workspace_code=workspace.code, title="Выпуск", type=TYPE_EXTENDED)
    stage = await stage_create(task_code=task.code, title="Сборка")
    entry = await journal_create(task_code=task.code, type="decision", title="Берём SSE")
    note = await task_note_add(task_code=task.code, title="Схема потока")
    codes = {
        "TASK": f"TASK@{task.code}",
        "STAGE": f"STAGE@{stage.code}",
        "JOURNAL": f"JOURNAL@{entry.code}",
        "NOTE": f"NOTE@{note.code}",
    }
    entities = {
        "TASK": "tasks.task",
        "STAGE": "tasks.stage",
        "JOURNAL": "tasks.journal",
        "NOTE": "notes.note",
    }
    await feed()

    for (prefix, field), handler in MCP_CONTENT_HANDLERS.items():
        await handler.set(codes[prefix], text=f"текст {field}")
        updated = _find(await feed(), entities[prefix], "updated")
        assert updated["ids"] == [codes[prefix]], (prefix, field)


async def test_a_task_note_reaches_the_feed_as_the_document_and_as_the_tasks_link(
    workspace, feed
):
    """The task page redraws its list from ``tasks.note`` (ref — the task); the document page
    follows ``notes.note``. One add is both, under the same code."""
    task = await task_create(workspace_code=workspace.code, title="Выпуск")
    await feed()

    note = await task_note_add(task_code=task.code, title="Схема потока")

    changes = await feed()
    link = _find(changes, "tasks.note", "created")
    document = _find(changes, "notes.note", "created")
    assert link["ids"] == document["ids"] == [f"NOTE@{note.code}"]
    assert link["refs"] == [f"TASK@{task.code}"]


async def test_a_task_note_soft_delete_reaches_the_feed_as_the_document_only(workspace, feed):
    """Pinned as built: a soft delete marks the document, the link is untouched — so the feed
    says ``notes.note`` updated and nothing about ``tasks.note``. A task page that lists notes
    must follow its notes' codes on ``notes.note``, not only ``tasks.note`` by task."""
    from src.modules.notes.crud.note import note_delete

    task = await task_create(workspace_code=workspace.code, title="Выпуск")
    note = await task_note_add(task_code=task.code, title="Схема потока")
    await feed()

    await note_delete(note.code)

    changes = await feed()
    assert [(c["entity"], c["event"], c["ids"]) for c in changes] == [
        ("notes.note", "updated", [f"NOTE@{note.code}"])
    ]


async def test_a_refused_content_edit_publishes_nothing(workspace, feed):
    from src.modules.tasks.mcp.content.task import McpTaskResultHandler

    task = await task_create(workspace_code=workspace.code, title="Выпуск", type=TYPE_EXTENDED)
    await feed()

    with pytest.raises(ValueError, match="too many"):
        await McpTaskResultHandler().set(f"TASK@{task.code}", text="я" * 5000)
    assert await feed() == []
