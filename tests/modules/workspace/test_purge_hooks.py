"""The "before final deletion" hooks: what the modules above collect inside the deleting
transaction, and what they do once it has committed.

The module knows no entity of theirs; these tests register stand-ins and read what each one saw.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select

from src.modules.workspace.crud import workspace as workspace_crud
from src.modules.workspace.models.workspace import Workspace
from src.modules.workspace.purge import (
    WorkspacePurgeHook,
    register_purge_hook,
    registered_purge_hooks,
    reset_purge_hooks,
)

pytestmark = pytest.mark.db


@pytest.fixture(autouse=True)
def no_hooks():
    reset_purge_hooks()
    yield
    reset_purge_hooks()


class Recorder:
    """A hook that notes whether the workspace row was still there when it collected, and when
    its after-commit step ran."""

    def __init__(self, key: str, log: list[str], *, fails_after: bool = False) -> None:
        self.key = key
        self.log = log
        self.fails_after = fails_after

    async def before_purge(self, session, workspace_code: str):
        row = await session.scalar(select(Workspace).where(Workspace.code == workspace_code))
        self.log.append(f"{self.key}: collected, row {'there' if row else 'gone'}")

        async def after() -> None:
            exists = await workspace_crud.workspace_get(workspace_code, include_deleted=True)
            self.log.append(f"{self.key}: after commit, row {'there' if exists else 'gone'}")
            if self.fails_after:
                raise RuntimeError("release failed")

        return after

    def hook(self) -> WorkspacePurgeHook:
        return WorkspacePurgeHook(key=self.key, before_purge=self.before_purge)


async def test_a_purge_collects_before_the_cascade_and_acts_after_the_commit(db):
    log: list[str] = []
    register_purge_hook(Recorder("b", log).hook())
    register_purge_hook(Recorder("a", log).hook())
    workspace = await workspace_crud.workspace_create(title="Под снос")

    assert await workspace_crud.workspace_delete(workspace.code, hard=True) is True

    assert log == [
        "a: collected, row there",
        "b: collected, row there",
        "a: after commit, row gone",
        "b: after commit, row gone",
    ]


async def test_a_failing_after_step_does_not_stop_the_others_or_undo_the_purge(db):
    log: list[str] = []
    register_purge_hook(Recorder("a", log, fails_after=True).hook())
    register_purge_hook(Recorder("b", log).hook())
    workspace = await workspace_crud.workspace_create(title="Под снос")

    assert await workspace_crud.workspace_delete(workspace.code, hard=True) is True

    assert "b: after commit, row gone" in log
    assert await workspace_crud.workspace_get(workspace.code, include_deleted=True) is None


async def test_a_soft_delete_and_a_missing_workspace_call_no_hook(db):
    log: list[str] = []
    register_purge_hook(Recorder("a", log).hook())
    workspace = await workspace_crud.workspace_create(title="Остаётся")

    await workspace_crud.workspace_delete(workspace.code)
    assert await workspace_crud.workspace_delete("0000000000", hard=True) is False

    assert log == []


def test_registering_a_key_again_replaces_it():
    first = WorkspacePurgeHook(key="tasks", before_purge=Recorder("x", []).before_purge)
    second = WorkspacePurgeHook(key="tasks", before_purge=Recorder("y", []).before_purge)

    register_purge_hook(first)
    register_purge_hook(second)

    assert [hook.before_purge for hook in registered_purge_hooks()] == [second.before_purge]
