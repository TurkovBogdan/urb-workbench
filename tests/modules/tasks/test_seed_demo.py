"""The demo seeder (``tools/seed_demo.py``) writes what its specs say — through the real CRUD.

The seeder reads specs with ``dict.get``: a key renamed in the model and left behind in a spec
(``body`` after the plan became ``plan``) used to seed an empty field without a word. So the
whole demo is seeded here, and every text a spec carries is read back.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from src.modules.tasks.crud import task as task_crud

pytestmark = pytest.mark.db

_SEEDER = Path(__file__).resolve().parents[3] / "tools" / "seed_demo.py"
_TEXT_FIELDS = ("description", "context", "constraints", "criteria", "plan", "progress", "result")


@pytest.fixture(scope="module")
def seeder():
    spec = importlib.util.spec_from_file_location("seed_demo", _SEEDER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _walk(specs: list[dict]):
    for spec in specs:
        yield spec
        yield from _walk(spec.get("children", []))


async def test_every_text_of_every_demo_task_lands(db, seeder):
    plan = [
        (seeder.WORKSPACES[0], seeder.DEV_TASKS),
        (seeder.WORKSPACES[1], seeder.PERSONAL_TASKS),
        (seeder.WORKSPACES[2], seeder.CLIENT_TASKS),
    ]
    stored = {}
    for workspace_spec, tasks in plan:
        report = await seeder.seed_workspace(workspace_spec, tasks)
        for row in await task_crud.task_list_by_workspace(report["code"], include_deleted=True):
            stored[row.title] = await task_crud.task_get(row.code, include_deleted=True)

    checked = 0
    for spec in _walk([task for _, tasks in plan for task in tasks]):
        for field in _TEXT_FIELDS:
            if field in spec:
                assert getattr(stored[spec["title"]], field) == spec[field], (spec["title"], field)
                checked += 1

    # The sweep reached the demo's texts — plans among them — rather than passing over nothing.
    assert checked > 30
    assert sum(1 for spec in _walk(seeder.DEV_TASKS) if spec.get("plan")) >= 5


async def test_an_unknown_key_in_a_task_spec_fails_the_seeding(db, workspace, seeder):
    with pytest.raises(ValueError, match=r"unknown keys: \['body'\]"):
        await seeder.seed_task(
            workspace_code=workspace.code, spec={"title": "Задача", "body": "план"}, groups={}
        )

    assert await task_crud.task_list_by_workspace(workspace.code) == []
