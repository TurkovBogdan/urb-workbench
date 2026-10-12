"""Mounting: only live codexes into live workspaces, once; the canvas and the workspace's order
over every codex, which a switch never moves; the agent's right to write; a deleted codex vanishing
from every canvas and coming back with its mounts."""

from __future__ import annotations

import pytest

from src.core.database import session_scope
from src.modules.codex.crud.codex import codex_create, codex_delete, codex_restore
from src.modules.codex.crud.mount import (
    mount_add,
    mount_get,
    mount_list,
    mount_remove,
    mount_reorder,
    mount_set_agent_can_edit,
    workspace_codexes,
)
from src.modules.codex.models import CodexMount
from src.modules.codex.rules import agent_may_write
from src.modules.workspace.crud.workspace import workspace_create, workspace_delete

pytestmark = pytest.mark.db


@pytest.fixture
async def python(db):
    return await codex_create(segment="python", title="Python")


async def _canvas(workspace) -> list[str]:
    return [codex.segment for _, codex in await mount_list(workspace.code)]


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
    vue = await codex_create(segment="vue", title="Vue")
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
    vue = await codex_create(segment="vue", title="Vue")
    sql = await codex_create(segment="sql", title="SQL")
    for codex in (python, vue, sql):
        await mount_add(codex.code, workspace.code)
    assert await _canvas(workspace) == ["python", "vue", "sql"]

    await mount_reorder(sql.code, workspace.code, after_code=None)
    assert await _canvas(workspace) == ["sql", "python", "vue"]

    await mount_reorder(sql.code, workspace.code, after_code=vue.code)
    assert await _canvas(workspace) == ["python", "vue", "sql"]


async def _order(workspace) -> list[tuple[str, bool]]:
    """The workspace's order over every codex: segment and whether it is switched on."""
    return [
        (codex.segment, bool(row and row.enabled))
        for codex, row in await workspace_codexes(workspace.code)
    ]


async def test_reorder_after_a_codex_not_in_the_order_is_refused(workspace, python):
    await mount_add(python.code, workspace.code)

    with pytest.raises(ValueError, match="not a codex of this workspace's order"):
        await mount_reorder(python.code, workspace.code, after_code="0000000000")


async def test_switching_off_and_on_keeps_the_codex_in_its_place(workspace, python):
    vue = await codex_create(segment="vue", title="Vue")
    sql = await codex_create(segment="sql", title="SQL")
    for codex in (python, vue, sql):
        await mount_add(codex.code, workspace.code)
    assert await _order(workspace) == [("python", True), ("vue", True), ("sql", True)]

    assert await mount_remove(vue.code, workspace.code)
    assert await _order(workspace) == [("python", True), ("vue", False), ("sql", True)]
    assert await _canvas(workspace) == ["python", "sql"]

    await mount_add(vue.code, workspace.code)
    assert await _order(workspace) == [("python", True), ("vue", True), ("sql", True)]


async def test_switching_off_drops_the_agent_right_and_switching_on_does_not_return_it(
    workspace, python
):
    await mount_add(python.code, workspace.code, agent_can_edit=True)
    await mount_remove(python.code, workspace.code)

    async with session_scope() as s:
        row = await s.get(CodexMount, (python.code, workspace.code))
        assert row is not None and not row.enabled and not row.agent_can_edit
    assert await mount_set_agent_can_edit(python.code, workspace.code, True) is None

    await mount_add(python.code, workspace.code)
    assert not agent_may_write(await mount_get(python.code, workspace.code))


async def test_never_placed_codexes_stand_after_the_placed_by_title(workspace, python):
    await codex_create(segment="vue", title="Vue")
    await codex_create(segment="angular", title="Angular")
    await mount_add(python.code, workspace.code)

    assert await _order(workspace) == [("python", True), ("angular", False), ("vue", False)]


async def test_a_switched_off_codex_is_moved_like_any_other(workspace, python):
    vue = await codex_create(segment="vue", title="Vue")
    await mount_add(python.code, workspace.code)

    await mount_reorder(vue.code, workspace.code, after_code=None)
    assert await _order(workspace) == [("vue", False), ("python", True)]

    await mount_add(vue.code, workspace.code)
    assert await _order(workspace) == [("vue", True), ("python", True)]
    assert await _canvas(workspace) == ["vue", "python"]


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
