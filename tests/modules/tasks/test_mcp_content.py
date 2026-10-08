"""workbench MCP: the content editor — every field, every action, every refusal.

Eight content fields across three entities are edited by the same four tools, each field through
its own handler. What is checked is not only that the text got written but WHAT comes back — the
agent sent the text itself, and the answer's value lies exactly in what it did not know: how the
insert landed and how far the cut reached. And every refusal is checked against the data after
it: a tool that refuses after writing reads "nothing happened" to the agent while half of it did.
"""

from __future__ import annotations

import pytest
from fastmcp.exceptions import ToolError

from src.modules.tasks.constants import (
    BODY_MAX,
    CONSTRAINTS_MAX,
    CONTEXT_MAX,
    CRITERIA_MAX,
    JOURNAL_BODY_MAX,
    JOURNAL_DECISION,
    PLAN_MAX,
    PROGRESS_MAX,
    RESULT_MAX,
    STATUS_DONE,
    STATUS_IN_PROGRESS,
    TYPE_EXTENDED,
    TYPE_SIMPLE,
    TYPE_STANDARD,
)
from src.modules.tasks.crud import journal as journal_crud
from src.modules.tasks.crud import stage as stage_crud
from src.modules.tasks.crud import task as task_crud
from src.modules.tasks.mcp.content.registry import MCP_CONTENT_HANDLERS
from src.modules.workspace.crud.workspace import workspace_create

pytestmark = pytest.mark.db

# Every content field and its cap — the registry must hold exactly these.
FIELDS = [
    ("TASK", "context", CONTEXT_MAX),
    ("TASK", "constraints", CONSTRAINTS_MAX),
    ("TASK", "criteria", CRITERIA_MAX),
    ("TASK", "plan", PLAN_MAX),
    ("TASK", "progress", PROGRESS_MAX),
    ("TASK", "result", RESULT_MAX),
    ("STAGE", "body", BODY_MAX),
    ("JOURNAL", "body", JOURNAL_BODY_MAX),
]
FIELD_IDS = [f"{prefix}.{field}" for prefix, field, _ in FIELDS]

BASE_TEXT = "## А\nстарое\n\n## Б\nхвост\n"


@pytest.fixture
async def task(workspace):
    return await task_crud.task_create(
        workspace_code=workspace.code, title="Тарифы", type=TYPE_EXTENDED
    )


@pytest.fixture
async def stage(task):
    return await stage_crud.stage_create(task_code=task.code, title="Схема")


@pytest.fixture
async def entry(task):
    return await journal_crud.journal_create(
        task_code=task.code, type=JOURNAL_DECISION, title="Решение"
    )


@pytest.fixture
async def codes(call, workspace, task, stage, entry) -> dict[str, str]:
    """The session bound to the workspace; a code per prefix, the way the agent passes it."""
    await call("workspace_use", workspace_code=workspace.code)
    return {
        "TASK": f"TASK@{task.code}",
        "STAGE": f"STAGE@{stage.code}",
        "JOURNAL": f"JOURNAL@{entry.code}",
    }


@pytest.fixture
async def bound(codes) -> str:
    """The task code — most seam and section checks run on its plan."""
    return codes["TASK"]


async def stored(prefix: str, code: str, field: str) -> str:
    """The field as it stands in the database, read past the tools."""
    bare = code.split("@", 1)[1]
    if prefix == "TASK":
        row = await task_crud.task_get(bare, include_deleted=True)
    elif prefix == "STAGE":
        row = await stage_crud.stage_get(bare)
    else:
        row = await journal_crud.journal_get(bare)
    return getattr(row, field)


async def plan_of(code: str) -> str:
    return await stored("TASK", code, "plan")


# ── the set of tools and fields ───────────────────────────────────────────────


async def test_the_registry_holds_exactly_the_content_fields():
    assert {(prefix, field) for prefix, field, _ in FIELDS} == set(MCP_CONTENT_HANDLERS)
    for prefix, field, limit in FIELDS:
        assert MCP_CONTENT_HANDLERS[(prefix, field)].limit == limit


async def test_every_long_text_column_has_a_handler_and_no_short_one_does():
    """Totality against the models, not against a list: a long markdown column added later
    without a handler fails here. "Long" is the line the module draws — wider than the 1024 of
    ``evidence`` and ``resolution``, which are pointers and verdicts, not content."""
    from sqlalchemy import String

    from src.modules.tasks.models.journal import TasksJournal
    from src.modules.tasks.models.stage import TasksStage
    from src.modules.tasks.models.task import TasksTask

    models = {"TASK": TasksTask, "STAGE": TasksStage, "JOURNAL": TasksJournal}
    long_columns = {
        (prefix, column.name)
        for prefix, model in models.items()
        for column in model.__table__.columns
        if isinstance(column.type, String) and (column.type.length or 0) > 1024
    }

    assert len(long_columns) == 8
    assert long_columns == set(MCP_CONTENT_HANDLERS)
    for (prefix, field), handler in MCP_CONTENT_HANDLERS.items():
        assert handler.limit == models[prefix].__table__.columns[field].type.length


async def test_content_tools_replace_the_body_tools(mcp):
    names = {tool.name for tool in await mcp.list_tools()}

    assert {"content_set", "content_replace", "content_set_section", "content_add"} <= names
    assert not {name for name in names if name.startswith("body_")}


async def test_field_is_a_required_argument_of_every_content_tool(mcp):
    """No default field: a call that does not say which field is not assembled at all."""
    for tool in await mcp.list_tools():
        if tool.name.startswith("content_"):
            assert "field" in tool.inputSchema["required"], tool.name


# ── every field × every action ────────────────────────────────────────────────


@pytest.mark.parametrize(("prefix", "field", "limit"), FIELDS, ids=FIELD_IDS)
async def test_set_replaces_the_field_whole(call, codes, prefix, field, limit):
    code = codes[prefix]

    answer = await call("content_set", code=code, field=field, text=BASE_TEXT)

    assert answer == {"code": code, "field": field, "length": len(BASE_TEXT)}
    assert await stored(prefix, code, field) == BASE_TEXT


@pytest.mark.parametrize(("prefix", "field", "limit"), FIELDS, ids=FIELD_IDS)
async def test_replace_swaps_one_fragment(call, codes, prefix, field, limit):
    code = codes[prefix]
    await call("content_set", code=code, field=field, text=BASE_TEXT)

    answer = await call("content_replace", code=code, field=field, find="старое", text="новое")

    assert (answer["field"], answer["replaced"]) == (field, 1)
    assert answer["edits"] == ["## А\n<text>\n\n## Б\nхвост\n"]
    assert await stored(prefix, code, field) == BASE_TEXT.replace("старое", "новое")


@pytest.mark.parametrize(("prefix", "field", "limit"), FIELDS, ids=FIELD_IDS)
async def test_set_section_rewrites_one_section(call, codes, prefix, field, limit):
    code = codes[prefix]
    await call("content_set", code=code, field=field, text=BASE_TEXT)

    cut = await call(
        "content_set_section", code=code, field=field, heading="## А", text="## А\nновое\n"
    )

    assert (cut["field"], cut["removed"], cut["stopped_at"]) == (field, "## А\nстарое\n", "## Б")
    assert await stored(prefix, code, field) == "## А\nновое\n\n## Б\nхвост\n"


@pytest.mark.parametrize(("prefix", "field", "limit"), FIELDS, ids=FIELD_IDS)
async def test_add_appends_at_the_end(call, codes, prefix, field, limit):
    """Appending is how a progress entry is written — and it works the same on every field."""
    code = codes[prefix]
    await call("content_set", code=code, field=field, text=BASE_TEXT)

    added = await call("content_add", code=code, field=field, text="- ещё\n", position="end")

    assert (added["field"], added["edit"]) == (field, BASE_TEXT + "<text>")
    assert await stored(prefix, code, field) == BASE_TEXT + "- ещё\n"


async def test_fields_of_one_entity_do_not_bleed_into_each_other(call, bound):
    for field in ("context", "constraints", "criteria", "plan", "progress", "result"):
        await call("content_set", code=bound, field=field, text=f"текст {field}")

    for field in ("context", "constraints", "criteria", "plan", "progress", "result"):
        assert await stored("TASK", bound, field) == f"текст {field}"


async def test_a_journal_entry_quoted_by_its_retired_note_code_is_edited(call, codes, entry):
    """``NOTE@`` was the journal's code until 2026-10-09; an agent holding one still reaches the
    entry, and the answer tells it the current code."""
    answer = await call("content_set", code=f"note@{entry.code.lower()}", field="body", text="х")

    assert answer["code"] == codes["JOURNAL"]
    assert await stored("JOURNAL", codes["JOURNAL"], "body") == "х"


async def test_a_lower_case_code_is_answered_in_upper_case(call, bound):
    answer = await call("content_set", code=bound.lower(), field="plan", text="х")

    assert answer["code"] == bound


# ── which field ───────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("prefix", "field", "where"),
    [
        ("TASK", "title", "task_update"),
        ("TASK", "description", "task_update"),
        ("STAGE", "title", "stage_update"),
        ("STAGE", "description", "stage_update"),
        ("STAGE", "evidence", "stage_close"),
        ("JOURNAL", "title", "journal_add"),
        ("JOURNAL", "resolution", "journal_resolve"),
    ],
)
async def test_a_field_that_is_not_content_is_refused_naming_its_tool(
    call, codes, prefix, field, where
):
    code = codes[prefix]
    before = await stored(prefix, code, field)

    with pytest.raises(ToolError, match=f"is not content — it is set with {where}"):
        await call("content_set", code=code, field=field, text="переписал")

    assert await stored(prefix, code, field) == before


async def test_an_unknown_field_lists_what_the_type_has(call, bound):
    """``body`` is the old name of the plan: the refusal shows the new one."""
    with pytest.raises(ToolError, match="no content field 'body'.*plan, progress, result"):
        await call("content_set", code=bound, field="body", text="х")

    assert await plan_of(bound) == ""


async def test_a_stage_has_only_its_body(call, codes):
    with pytest.raises(ToolError, match="no content field 'plan'. Its content fields: body"):
        await call("content_set", code=codes["STAGE"], field="plan", text="х")


@pytest.mark.parametrize("code", ["TASKGROUP@0000000000", "WORKSPACE@0000000000", "0000000000"])
async def test_a_code_with_no_content_is_refused(call, bound, code):
    with pytest.raises(ToolError, match="has no content to edit"):
        await call("content_set", code=code, field="body", text="х")


# ── seam ──────────────────────────────────────────────────────────────────────


async def test_the_answer_is_the_seam_not_the_text_the_agent_sent(call, bound):
    """The text sent is not echoed back: the agent has just written it and knows it.

    What comes back is what it did not know — what the insert butts against on the left and right.
    """
    await call("content_set", code=bound, field="plan", text="начало и конец")

    added = await call(
        "content_add", code=bound, field="plan", text="СЕРЕДИНА", position="after", anchor="и "
    )

    assert "СЕРЕДИНА" not in added["edit"]
    assert added["edit"] == "начало и <text>конец"
    assert await plan_of(bound) == "начало и СЕРЕДИНАконец"


async def test_add_at_the_start_and_before_an_anchor(call, bound):
    await call("content_set", code=bound, field="plan", text="середина")

    await call("content_add", code=bound, field="plan", text="начало ", position="start")
    await call(
        "content_add", code=bound, field="plan", text="[", position="before", anchor="середина"
    )

    assert await plan_of(bound) == "начало [середина"


async def test_a_long_text_marks_where_the_window_was_cut(call, bound):
    await call("content_set", code=bound, field="plan", text="я" * 300 + "ЯКОРЬ" + "б" * 300)

    added = await call(
        "content_add", code=bound, field="plan", text="x", position="before", anchor="ЯКОРЬ"
    )

    # An ellipsis only where the window is cut mid-text — the edge is visible as it is.
    assert added["edit"].startswith("…") and added["edit"].endswith("…")


async def test_replace_all_returns_one_seam_per_occurrence(call, bound):
    await call("content_set", code=bound, field="plan", text="раз. два. раз.")

    replaced = await call(
        "content_replace", code=bound, field="plan", find="раз", text="ОДИН", mode="all"
    )

    assert replaced["replaced"] == 2 and len(replaced["edits"]) == 2
    assert await plan_of(bound) == "ОДИН. два. ОДИН."


# ── refusals leave the field as it was ────────────────────────────────────────


async def test_a_fragment_that_repeats_is_refused_rather_than_guessed(call, bound):
    await call("content_set", code=bound, field="plan", text="раз. два. раз.")

    with pytest.raises(ToolError, match="occurs 2 times"):
        await call("content_replace", code=bound, field="plan", find="раз", text="ОДИН")

    assert await plan_of(bound) == "раз. два. раз."


async def test_a_fragment_that_is_not_there_is_an_error_in_both_modes(call, bound):
    await call("content_set", code=bound, field="plan", text="раз")

    for mode in ("single", "all"):
        with pytest.raises(ToolError, match="is not in the text"):
            await call(
                "content_replace", code=bound, field="plan", find="три", text="х", mode=mode
            )

    assert await plan_of(bound) == "раз"


async def test_an_unknown_mode_or_position_writes_nothing(call, bound):
    await call("content_set", code=bound, field="plan", text="раз")

    with pytest.raises(ToolError, match="mode must be"):
        await call("content_replace", code=bound, field="plan", find="раз", text="х", mode="any")
    with pytest.raises(ToolError, match="position must be one of"):
        await call("content_add", code=bound, field="plan", text="х", position="middle")
    with pytest.raises(ToolError, match="needs an anchor"):
        await call("content_add", code=bound, field="plan", text="х", position="after")

    assert await plan_of(bound) == "раз"


async def test_an_anchor_must_be_there_and_unique(call, bound):
    await call("content_set", code=bound, field="plan", text="раз. раз.")

    with pytest.raises(ToolError, match="not found"):
        await call("content_add", code=bound, field="plan", text="х", position="after", anchor="два")
    with pytest.raises(ToolError, match="occurs 2 times"):
        await call("content_add", code=bound, field="plan", text="х", position="after", anchor="раз")

    assert await plan_of(bound) == "раз. раз."


# ── sections ──────────────────────────────────────────────────────────────────


async def test_a_section_runs_to_the_next_heading_of_its_level_or_higher(call, bound):
    await call(
        "content_set",
        code=bound,
        field="plan",
        text="## Подход\nпроза\n\n### Деталь\nещё\n\n## Файлы\nсписок\n",
    )

    cut = await call(
        "content_set_section", code=bound, field="plan", heading="## Подход", text="## Подход\nново\n"
    )

    # The subsection went along with the section; the next section of the same level did not.
    assert "### Деталь" in cut["removed"]
    assert cut["stopped_at"] == "## Файлы"


async def test_a_hash_inside_a_fence_is_code_and_does_not_end_a_section(call, bound):
    await call(
        "content_set",
        code=bound,
        field="plan",
        text="## Подход\n```sh\n# это комментарий\nls\n```\nхвост\n\n## Файлы\nсписок\n",
    )

    cut = await call(
        "content_set_section", code=bound, field="plan", heading="## Подход", text="## Подход\nново\n"
    )

    assert "хвост" in cut["removed"] and cut["stopped_at"] == "## Файлы"


async def test_a_repeating_heading_is_refused_with_the_way_out(call, bound):
    text = "## А\n### Шаг\n## Б\n### Шаг\n"
    await call("content_set", code=bound, field="plan", text=text)

    with pytest.raises(ToolError, match="occurs 2 times"):
        await call(
            "content_set_section", code=bound, field="plan", heading="### Шаг", text="### Шаг\nх\n"
        )

    assert await plan_of(bound) == text


async def test_a_path_singles_out_a_repeating_heading(call, bound):
    await call(
        "content_set", code=bound, field="plan", text="## А\n### Шаг\nстарое\n## Б\n### Шаг\nчужое\n"
    )

    cut = await call(
        "content_set_section",
        code=bound,
        field="plan",
        heading="## А > ### Шаг",
        text="### Шаг\nновое\n",
    )

    assert "старое" in cut["removed"] and "чужое" not in cut["removed"]
    # Spliced verbatim: the trailing newline of the new section stays as a blank line.
    assert await plan_of(bound) == "## А\n### Шаг\nновое\n\n## Б\n### Шаг\nчужое\n"


async def test_a_plain_string_is_not_a_heading(call, bound):
    await call("content_set", code=bound, field="plan", text="## Подход\nпроза\n")

    with pytest.raises(ToolError, match="is not a markdown heading"):
        await call("content_set_section", code=bound, field="plan", heading="Подход", text="х")


async def test_a_missing_heading_is_refused(call, bound):
    await call("content_set", code=bound, field="plan", text="## Подход\nпроза\n")

    with pytest.raises(ToolError, match="is not in the text"):
        await call("content_set_section", code=bound, field="plan", heading="## Риски", text="х")

    assert await plan_of(bound) == "## Подход\nпроза\n"


# ── limit ─────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(("prefix", "field", "limit"), FIELDS, ids=FIELD_IDS)
async def test_the_whole_limit_fits(call, codes, prefix, field, limit):
    code = codes[prefix]

    answer = await call("content_set", code=code, field=field, text="я" * limit)

    assert answer["length"] == limit
    assert len(await stored(prefix, code, field)) == limit


@pytest.mark.parametrize(("prefix", "field", "limit"), FIELDS, ids=FIELD_IDS)
async def test_the_limit_names_the_length_of_the_result_and_writes_nothing(
    call, codes, prefix, field, limit
):
    """The agent appended five characters to an almost full field and hit the limit NOT because
    of them. Tell it the length of the piece it sent, and it will shorten the wrong place."""
    code = codes[prefix]
    await call("content_set", code=code, field=field, text="я" * (limit - 2))

    with pytest.raises(ToolError) as caught:
        await call("content_add", code=code, field=field, text="ххххх", position="end")

    assert f"{limit + 3} characters long" in str(caught.value)
    assert "3 too many" in str(caught.value)
    assert await stored(prefix, code, field) == "я" * (limit - 2)


@pytest.mark.parametrize(("prefix", "field", "limit"), FIELDS, ids=FIELD_IDS)
async def test_an_oversized_set_is_refused_not_trimmed(call, codes, prefix, field, limit):
    code = codes[prefix]
    await call("content_set", code=code, field=field, text="было")

    with pytest.raises(ToolError, match="1 too many"):
        await call("content_set", code=code, field=field, text="я" * (limit + 1))

    assert await stored(prefix, code, field) == "было"


@pytest.mark.parametrize(("prefix", "field", "limit"), FIELDS, ids=FIELD_IDS)
async def test_a_nul_character_is_refused_on_every_field(call, codes, prefix, field, limit):
    """PostgreSQL cannot store U+0000 in text and fails the write with an encoding error, while
    SQLite keeps it: the same call would pass in dev and break in production. Refused here, on
    both, before anything is written."""
    code = codes[prefix]
    await call("content_set", code=code, field=field, text="было")

    with pytest.raises(ToolError, match="NUL"):
        await call("content_add", code=code, field=field, text="a\x00b", position="end")

    assert await stored(prefix, code, field) == "было"


# ── the type of the task ──────────────────────────────────────────────────────

STANDARD_FIELDS = ["constraints", "criteria", "plan", "progress", "result"]


@pytest.mark.parametrize("field", STANDARD_FIELDS)
async def test_a_simple_task_refuses_the_fields_it_does_not_have(call, workspace, field):
    """A simple task is a title, a goal and the context: the page shows nothing else, so text
    written there would be seen by nobody. Refused loudly, with the way out — as journal_add and
    stage_add already refuse on a type that has no journal or stages."""
    await call("workspace_use", workspace_code=workspace.code)
    task = await task_crud.task_create(
        workspace_code=workspace.code, title="Простая", type=TYPE_SIMPLE, **{field: "было"}
    )
    code = f"TASK@{task.code}"

    for action, args in (
        ("content_set", {"text": "х"}),
        ("content_add", {"text": "х", "position": "end"}),
        ("content_replace", {"find": "было", "text": "х"}),
        ("content_set_section", {"heading": "## А", "text": "х"}),
    ):
        with pytest.raises(ToolError, match=r"is simple.*type=\"standard\""):
            await call(action, code=code, field=field, **args)

    assert await stored("TASK", code, field) == "было"


async def test_a_simple_task_keeps_its_context_editable(call, workspace):
    """The context is part of a simple task — the refusal is for the fields it does not show."""
    await call("workspace_use", workspace_code=workspace.code)
    task = await task_crud.task_create(workspace_code=workspace.code, title="Простая")
    code = f"TASK@{task.code}"

    await call("content_set", code=code, field="context", text="вводные")

    assert await stored("TASK", code, "context") == "вводные"


@pytest.mark.parametrize("field", STANDARD_FIELDS)
async def test_raising_the_type_opens_the_field(call, workspace, field):
    await call("workspace_use", workspace_code=workspace.code)
    task = await task_crud.task_create(workspace_code=workspace.code, title="Простая")
    code = f"TASK@{task.code}"
    with pytest.raises(ToolError, match="is simple"):
        await call("content_set", code=code, field=field, text="рано")

    await call("task_update", task_code=code, type=TYPE_STANDARD)
    await call("content_set", code=code, field=field, text="после подъёма типа")

    assert await stored("TASK", code, field) == "после подъёма типа"


# ── the state of the entity ───────────────────────────────────────────────────


async def test_the_body_of_a_running_and_a_closed_stage_stays_editable(call, codes, stage):
    """No freeze by status: the ban on a started stage's body was lifted with the content tools."""
    code = codes["STAGE"]
    await stage_crud.stage_update_status(stage.code, STATUS_IN_PROGRESS)
    await call("content_set", code=code, field="body", text="уточнил шаг")

    await stage_crud.stage_update(stage.code, evidence="pytest -q → ok")
    await stage_crud.stage_update_status(stage.code, STATUS_DONE)
    await call("content_add", code=code, field="body", text=" и закрыл", position="end")

    assert await stored("STAGE", code, "body") == "уточнил шаг и закрыл"


async def test_the_work_fields_stay_editable_on_any_task_status(call, bound):
    await call("task_status", task_code=bound, status="in_review")

    for field in ("plan", "progress", "result"):
        await call("content_set", code=bound, field=field, text="после сдачи")

    for field in ("plan", "progress", "result"):
        assert await stored("TASK", bound, field) == "после сдачи"


@pytest.mark.parametrize(("prefix", "field"), [("TASK", "plan"), ("STAGE", "body"), ("JOURNAL", "body")])
async def test_a_deleted_task_and_what_hangs_off_it_are_not_edited(
    call, codes, task, prefix, field
):
    code = codes[prefix]
    await call("content_set", code=code, field=field, text="до удаления")
    await task_crud.task_delete(task.code)

    with pytest.raises(ToolError, match="is deleted"):
        await call("content_set", code=code, field=field, text="после удаления")

    assert await stored(prefix, code, field) == "до удаления"


@pytest.mark.parametrize(("prefix", "field"), [("TASK", "plan"), ("STAGE", "body"), ("JOURNAL", "body")])
async def test_a_code_of_another_workspace_is_refused_and_not_written(call, bound, prefix, field):
    """Each prefix finds its workspace its own way — a stage and an entry through their task —
    so the fence is checked on all three."""
    stranger = await workspace_create(title="Личное")
    alien_task = await task_crud.task_create(
        workspace_code=stranger.code, title="Чужая", type=TYPE_EXTENDED, plan="своё"
    )
    alien = {
        "TASK": alien_task.code,
        "STAGE": (
            await stage_crud.stage_create(task_code=alien_task.code, title="Шаг", body="своё")
        ).code,
        "JOURNAL": (
            await journal_crud.journal_create(
                task_code=alien_task.code, type=JOURNAL_DECISION, title="Решение", body="своё"
            )
        ).code,
    }
    code = f"{prefix}@{alien[prefix]}"

    with pytest.raises(ToolError, match="belongs to workspace .*'Личное'"):
        await call("content_set", code=code, field=field, text="чужое")

    assert await stored(prefix, code, field) == "своё"


async def test_a_refusal_after_the_row_was_touched_leaves_it_as_it_was(call, bound):
    """Every check runs before the write — but what actually holds "refused means unwritten" is
    the transaction: ``write_scope`` rolls back on the exception. Checked through a handler whose
    check touches the row and then refuses; reordering the checks in ``_apply`` would not show,
    a write that escaped the transaction would."""
    from src.modules.tasks.mcp.content.task import McpTaskPlanHandler

    class Touching(McpTaskPlanHandler):
        def check(self, row, task, code):
            row.title = "тронуто"
            row.plan = "тронуто"
            raise ValueError("refused after touching")

    await call("content_set", code=bound, field="plan", text="было")

    with pytest.raises(ValueError, match="refused after touching"):
        await Touching().set(bound, text="стало")

    stored_task = await task_crud.task_get(bound.split("@", 1)[1])
    assert (stored_task.title, stored_task.plan) == ("Тарифы", "было")


@pytest.mark.parametrize("prefix", ["TASK", "STAGE", "JOURNAL"])
async def test_a_code_that_does_not_exist_is_refused(call, bound, prefix):
    field = "plan" if prefix == "TASK" else "body"

    with pytest.raises(ToolError, match=f"{prefix}@0000000000 does not exist"):
        await call("content_set", code=f"{prefix}@0000000000", field=field, text="х")

    # The refusal wrote nowhere else: the session's own task kept its plan.
    assert await plan_of(bound) == ""
