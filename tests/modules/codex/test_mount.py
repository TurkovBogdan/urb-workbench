"""Mounting: only live codexes into live workspaces, once; the canvas and its order; the agent's
right to write; a deleted codex vanishing from every canvas and coming back with its mounts."""

from __future__ import annotations

import pytest

from src.modules.codex.crud.codex import codex_create, codex_delete, codex_restore
from src.modules.codex.crud.mount import (
    mount_add,
    mount_get,
    mount_list,
    mount_remove,
    mount_reorder,
    mount_set_agent_can_edit,
)
from src.modules.codex.rules import agent_may_write
from src.modules.workspace.crud.workspace import workspace_create, workspace_delete

pytestmark = pytest.mark.db


@pytest.fixture
async def python(db):
    return await codex_create(slug="python", title="Python")


async def _canvas(workspace) -> list[str]:
    return [codex.slug for _, codex in await mount_list(workspace.code)]


async def test_a_mount_shows_the_codex_in_that_workspace_only(workspace, python):
    elsewhere = await workspace_create(title="Личное")
    mount = await mount_add(python.code, workspace.code)

    assert agent_may_write(mount)
    assert await _canvas(workspace) == ["python"]
    assert await _canvas(elsewhere) == []
    assert await mount_get(python.code, elsewhere.code) is None


async def test_mounting_twice_is_refused(workspace, python):
    await mount_add(python.code, workspace.code)

    with pytest.raises(ValueError, match="already mounted"):
        await mount_add(python.code, workspace.code)
    assert await _canvas(workspace) == ["python"]


async def test_a_deleted_codex_or_workspace_cannot_be_mounted(workspace, python):
    vue = await codex_create(slug="vue", title="Vue")
    await codex_delete(vue.code)
    gone = await workspace_create(title="Архив")
    await workspace_delete(gone.code)

    with pytest.raises(ValueError, match="not a live codex"):
        await mount_add(vue.code, workspace.code)
    with pytest.raises(ValueError, match="not a live workspace"):
        await mount_add(python.code, gone.code)
    assert await _canvas(workspace) == []


async def test_the_agent_right_is_per_mount(workspace, python):
    elsewhere = await workspace_create(title="Личное")
    await mount_add(python.code, workspace.code)
    await mount_add(python.code, elsewhere.code, agent_can_edit=False)

    assert agent_may_write(await mount_get(python.code, workspace.code))
    assert not agent_may_write(await mount_get(python.code, elsewhere.code))

    await mount_set_agent_can_edit(python.code, workspace.code, False)
    assert not agent_may_write(await mount_get(python.code, workspace.code))


async def test_a_new_mount_lands_at_the_bottom_and_reorder_moves_it(workspace, python):
    vue = await codex_create(slug="vue", title="Vue")
    sql = await codex_create(slug="sql", title="SQL")
    for codex in (python, vue, sql):
        await mount_add(codex.code, workspace.code)
    assert await _canvas(workspace) == ["python", "vue", "sql"]

    await mount_reorder(sql.code, workspace.code, after_code=None)
    assert await _canvas(workspace) == ["sql", "python", "vue"]

    await mount_reorder(sql.code, workspace.code, after_code=vue.code)
    assert await _canvas(workspace) == ["python", "vue", "sql"]


async def test_reorder_after_a_codex_not_in_the_canvas_is_refused(workspace, python):
    vue = await codex_create(slug="vue", title="Vue")
    await mount_add(python.code, workspace.code)

    with pytest.raises(ValueError, match="not mounted into this workspace"):
        await mount_reorder(python.code, workspace.code, after_code=vue.code)


async def test_a_deleted_codex_leaves_every_canvas_and_returns_with_its_rights(
    workspace, python
):
    await mount_add(python.code, workspace.code, agent_can_edit=False)
    await codex_delete(python.code)

    assert await _canvas(workspace) == []
    assert await mount_get(python.code, workspace.code) is None

    await codex_restore(python.code)
    assert await _canvas(workspace) == ["python"]
    assert not agent_may_write(await mount_get(python.code, workspace.code))


async def test_unmounting(workspace, python):
    await mount_add(python.code, workspace.code)

    assert await mount_remove(python.code, workspace.code)
    assert not await mount_remove(python.code, workspace.code)
    assert await _canvas(workspace) == []
