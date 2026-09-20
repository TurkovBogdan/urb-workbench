"""workbench MCP: редактор тела — швы, границы разделов, лимит и запрет на застывший план.

Тело есть у трёх сущностей, и все три правятся одними инструментами. Проверяется не то, что
текст записался (это тривиально), а то, ЧТО возвращается: агент прислал текст сам, и ценность
ответа ровно в том, чего он не знал, — как вставка легла и как далеко ушёл вырез.
"""

from __future__ import annotations

import pytest
from fastmcp.exceptions import ToolError

from src.modules.tasks.constants import BODY_MAX, NOTE_DECISION, TYPE_EXTENDED
from src.modules.tasks.crud import note as note_crud
from src.modules.tasks.crud import stage as stage_crud
from src.modules.tasks.crud import task as task_crud

pytestmark = pytest.mark.db


@pytest.fixture
async def task(workspace):
    return await task_crud.task_create(
        workspace_code=workspace.code, title="Тарифы", type=TYPE_EXTENDED
    )


@pytest.fixture
async def bound(call, workspace, task):
    await call("workspace_use", workspace_code=workspace.code)
    return f"TASK@{task.code}"


# ── что вообще имеет тело ─────────────────────────────────────────────────────


async def test_all_three_bodies_are_edited_by_the_same_tools(call, bound, task, workspace):
    stage = await stage_crud.stage_create(task_code=task.code, title="Схема")
    note = await note_crud.note_create(
        task_code=task.code, type=NOTE_DECISION, title="Решение"
    )

    for code in (bound, f"STAGE@{stage.code}", f"NOTE@{note.code}"):
        assert (await call("body_set", code=code, text="Текст"))["length"] == 5


async def test_a_group_has_no_body_and_the_refusal_says_where_the_brief_lives(call, bound):
    with pytest.raises(ToolError, match="has no body to edit"):
        await call("body_set", code="GROUP@0000000000", text="х")


# ── шов ───────────────────────────────────────────────────────────────────────


async def test_the_answer_is_the_seam_not_the_text_the_agent_sent(call, bound):
    """Присланный текст назад не едет: агент его только что написал и знает.

    Возвращается то, чего он не знал, — во что вставка упёрлась слева и справа.
    """
    await call("body_set", code=bound, text="начало и конец")

    added = await call("body_add", code=bound, text="СЕРЕДИНА", position="after", anchor="и ")

    assert "СЕРЕДИНА" not in added["edit"]
    assert added["edit"] == "начало и <text>конец"


async def test_a_long_body_marks_where_the_window_was_cut(call, bound):
    await call("body_set", code=bound, text="я" * 300 + "ЯКОРЬ" + "б" * 300)

    added = await call("body_add", code=bound, text="x", position="before", anchor="ЯКОРЬ")

    # Многоточие только там, где окно обрезано серединой тела, — край виден и так.
    assert added["edit"].startswith("…") and added["edit"].endswith("…")


async def test_replace_all_returns_one_seam_per_occurrence(call, bound):
    await call("body_set", code=bound, text="раз. два. раз.")

    replaced = await call("body_replace", code=bound, find="раз", text="ОДИН", mode="all")

    assert replaced["replaced"] == 2 and len(replaced["edits"]) == 2


async def test_a_fragment_that_repeats_is_refused_rather_than_guessed(call, bound):
    await call("body_set", code=bound, text="раз. два. раз.")

    with pytest.raises(ToolError, match="occurs 2 times"):
        await call("body_replace", code=bound, find="раз", text="ОДИН")


async def test_a_fragment_that_is_not_there_is_an_error_in_both_modes(call, bound):
    await call("body_set", code=bound, text="раз")

    for mode in ("single", "all"):
        with pytest.raises(ToolError, match="is not in the body"):
            await call("body_replace", code=bound, find="три", text="х", mode=mode)


# ── разделы ───────────────────────────────────────────────────────────────────


async def test_a_section_runs_to_the_next_heading_of_its_level_or_higher(call, bound):
    await call(
        "body_set",
        code=bound,
        text="## Подход\nпроза\n\n### Деталь\nещё\n\n## Файлы\nсписок\n",
    )

    cut = await call("body_set_section", code=bound, heading="## Подход", text="## Подход\nново\n")

    # Подраздел уехал вместе с разделом, а следующий раздел того же уровня — нет.
    assert "### Деталь" in cut["removed"]
    assert cut["stopped_at"] == "## Файлы"


async def test_a_hash_inside_a_fence_is_code_and_does_not_end_a_section(call, bound):
    await call(
        "body_set",
        code=bound,
        text="## Подход\n```sh\n# это комментарий\nls\n```\nхвост\n\n## Файлы\nсписок\n",
    )

    cut = await call("body_set_section", code=bound, heading="## Подход", text="## Подход\nново\n")

    assert "хвост" in cut["removed"] and cut["stopped_at"] == "## Файлы"


async def test_a_repeating_heading_is_refused_with_the_way_out(call, bound):
    await call("body_set", code=bound, text="## А\n### Шаг\n## Б\n### Шаг\n")

    with pytest.raises(ToolError, match="occurs 2 times"):
        await call("body_set_section", code=bound, heading="### Шаг", text="### Шаг\nх\n")


async def test_a_path_singles_out_a_repeating_heading(call, bound):
    await call("body_set", code=bound, text="## А\n### Шаг\nстарое\n## Б\n### Шаг\nчужое\n")

    cut = await call(
        "body_set_section", code=bound, heading="## А > ### Шаг", text="### Шаг\nновое\n"
    )

    assert "старое" in cut["removed"] and "чужое" not in cut["removed"]


async def test_a_plain_string_is_not_a_heading(call, bound):
    await call("body_set", code=bound, text="## Подход\nпроза\n")

    with pytest.raises(ToolError, match="is not a markdown heading"):
        await call("body_set_section", code=bound, heading="Подход", text="х")


# ── лимит ─────────────────────────────────────────────────────────────────────


async def test_the_limit_names_the_length_of_the_result_not_of_the_piece_sent(call, bound):
    """Агент дописал две строки в почти полное тело и упёрся НЕ в них.

    Назови ему длину присланного куска — и он будет сокращать не то место.
    """
    await call("body_set", code=bound, text="я" * (BODY_MAX - 2))

    with pytest.raises(ToolError) as caught:
        await call("body_add", code=bound, text="ххххх", position="end")

    assert str(BODY_MAX + 3) in str(caught.value)
    assert "3 too many" in str(caught.value)


# ── застывший план ────────────────────────────────────────────────────────────


async def test_the_body_of_a_running_stage_is_frozen(call, bound, task):
    stage = await stage_crud.stage_create(task_code=task.code, title="Схема")
    await call("stage_update", stage_code=f"STAGE@{stage.code}", status="in_progress")

    with pytest.raises(ToolError, match="does not get rewritten"):
        await call("body_set", code=f"STAGE@{stage.code}", text="переписал")


async def test_the_plan_of_the_task_stays_editable_while_the_task_lives(call, bound):
    """Запрет — про этап, а не про длинный текст вообще: план прозой живёт с задачей."""
    await call("task_status", task_code=bound, status="in_progress")

    assert (await call("body_set", code=bound, text="уточнил подход"))["length"] == 14
