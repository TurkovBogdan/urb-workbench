"""workbench MCP: каталог навыков и показ страницы пользователю.

Навыки — файлы в модуле, и тест сторожит не их текст, а то, ради чего каталог существует:
первый уровень дёшев (имена и условия вызова, без текстов), у каждого навыка есть условие, и
неизвестное имя отвечает списком доступных, а не пустотой.
"""

from __future__ import annotations

import pytest
from fastmcp.exceptions import ToolError

from src.modules.tasks.constants import TYPE_EXTENDED
from src.modules.tasks.crud import note as note_crud
from src.modules.tasks.crud import stage as stage_crud
from src.modules.tasks.crud import task as task_crud
from src.modules.tasks.services.skills import list_skills

pytestmark = pytest.mark.db


async def test_the_catalogue_carries_conditions_and_no_text(call, db):
    rows = (await call("skills_list"))["result"]

    assert {row["name"] for row in rows} >= {"task-brief", "task-plan", "journal", "markdown"}
    for row in rows:
        # Описание — это УСЛОВИЕ вызова, а не тема: «read before…», а не «about briefs».
        assert row["description"].lower().startswith("read before"), row["name"]
        assert "text" not in row


async def test_a_skill_reads_whole(call, db):
    skill = await call("skill_get", skill_name="task-plan")

    assert "evidence" in skill["text"].lower()
    assert skill["section"] == ""


async def test_an_unknown_skill_answers_with_what_there_is(call, db):
    with pytest.raises(ToolError, match="Available: "):
        await call("skill_get", skill_name="как-жить")


def test_every_skill_file_declares_its_condition():
    """Навык без описания невидим на первом уровне — его просто никогда не откроют."""
    assert list_skills()
    for skill in list_skills():
        assert skill.description, skill.name


# ── показ ─────────────────────────────────────────────────────────────────────


@pytest.fixture
def no_browser(monkeypatch):
    """Браузер не дёргаем: тест про адрес, а не про то, что на машине есть чем открыть."""
    opened = []
    monkeypatch.setattr(
        "src.modules.tasks.mcp.interface.webbrowser.open",
        lambda url: opened.append(url) or True,
    )
    return opened


async def test_a_task_opens_its_own_page(call, workspace, no_browser):
    await call("workspace_use", workspace_code=workspace.code)
    task = await task_crud.task_create(workspace_code=workspace.code, title="Тарифы")

    url = await call("interface_open", code=f"TASK@{task.code}")

    assert url["result"].endswith(f"/tasks/task/TASK@{task.code}")
    assert no_browser == [url["result"]]


async def test_a_stage_and_an_entry_open_the_task_they_live_on(call, workspace, no_browser):
    await call("workspace_use", workspace_code=workspace.code)
    task = await task_crud.task_create(
        workspace_code=workspace.code, title="Тарифы", type=TYPE_EXTENDED
    )
    stage = await stage_crud.stage_create(task_code=task.code, title="Схема")
    note = await note_crud.note_create(task_code=task.code, type="fact", title="tariff.py:88")

    for code in (f"STAGE@{stage.code}", f"NOTE@{note.code}"):
        url = (await call("interface_open", code=code))["result"]
        assert url.endswith(f"/tasks/task/TASK@{task.code}")


async def test_a_workspace_and_a_group_open_the_list_they_are_a_row_in(call, workspace, no_browser):
    await call("workspace_use", workspace_code=workspace.code)

    url = (await call("interface_open", code=f"WORKSPACE@{workspace.code}"))["result"]

    assert url.endswith("/workspaces")


async def test_showing_a_foreign_workspace_is_refused_like_everything_else(
    call, workspace, no_browser
):
    """Открытие страницы — видимое действие на машине человека, и забор действует и здесь."""
    from src.modules.workspace.crud.workspace import workspace_create

    other = await workspace_create(title="Личное")
    await call("workspace_use", workspace_code=workspace.code)

    with pytest.raises(ToolError, match="hard boundary"):
        await call("interface_open", code=f"WORKSPACE@{other.code}")

    assert no_browser == []
