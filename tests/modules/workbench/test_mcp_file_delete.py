"""workbench MCP: ``delete(FILE@…)`` takes a file out of its place — and only where it is meant.

A file has one code in every place it is bound to. Without ``holder`` the call acts only when one
place is visible in the active workspace; with several it refuses, lists them and changes
nothing, and the repeat names the place. Bindings of other workspaces and of codexes not mounted
here are neither listed nor touched. Every refusal is checked by the state it leaves: the bindings
of both tables, the storage owners, the file's deletion mark.
"""

from __future__ import annotations

import pytest
from fastmcp.exceptions import ToolError

from src.modules.codex import files as codex_files
from src.modules.codex.crud import codex as codex_crud
from src.modules.codex.crud import file as codex_file_crud
from src.modules.codex.crud import mount as mount_crud
from src.modules.codex.crud import note as codex_note_crud
from src.modules.core_storage.dto import Owner
from src.modules.core_storage.services.files import file_get
from src.modules.core_storage.services.ownership import file_owners
from src.modules.tasks import files as task_files
from src.modules.tasks.constants import TYPE_EXTENDED
from src.modules.tasks.crud import file as task_file_crud
from src.modules.tasks.crud import note as task_note_crud
from src.modules.tasks.crud import stage as stage_crud
from src.modules.tasks.crud import task as task_crud
from src.modules.tasks.files import FilePlace
from src.modules.workspace.crud.workspace import workspace_create
from tests.modules.codex.file_support import codex_file_attach_bytes
from tests.modules.tasks.file_support import task_file_attach_bytes

pytestmark = pytest.mark.db

CONTENT = b"# schema\n"


@pytest.fixture
async def here(call, workspace, storage):
    await call("workspace_use", workspace_code=workspace.code)
    return workspace


@pytest.fixture
async def task(here):
    return await task_crud.task_create(workspace_code=here.code, title="Выпуск", type=TYPE_EXTENDED)


@pytest.fixture
async def other_task(here):
    return await task_crud.task_create(workspace_code=here.code, title="Отчёт")


@pytest.fixture
async def elsewhere():
    return await workspace_create(title="Личное")


async def _codex_note(workspace_code: str | None, *, writable: bool = True):
    codex = await codex_crud.codex_create(segment="python", title="Python")
    if workspace_code is not None:
        await mount_crud.mount_add(codex.code, workspace_code, agent_can_edit=writable)
    return await codex_note_crud.note_create(parent_code=codex.code, segment="test", title="Тесты")


async def _owners(code: str) -> set[Owner]:
    return {place.owner for place in await file_owners(code)}


async def _task_holders(code: str) -> set[str]:
    return {row.task_code for row in await task_file_crud.task_file_list_by_file(code)}


async def _note_holders(code: str) -> set[str]:
    return {row.note_code for row in await codex_file_crud.codex_file_list_by_file(code)}


async def _state(code: str) -> tuple:
    """Everything a deletion could have touched."""
    stored = await file_get(code, include_deleted=True)
    return (
        await _task_holders(code),
        await _note_holders(code),
        await _owners(code),
        stored.deleted_at is not None,
    )


async def _on_task(task_code: str, *, place: FilePlace = FilePlace()) -> str:
    bound = await task_file_attach_bytes(
        task_code, CONTENT, filename="schema.md", place=place
    )
    return bound.file_code


async def _also_on_task(task_code: str, file_code: str) -> None:
    await task_files.task_file_attach_existing(task_code, file_code)


async def _also_on_note(note_code: str, file_code: str) -> None:
    await codex_files.codex_file_attach_existing(note_code, file_code)


# ── one place ─────────────────────────────────────────────────────────────────


async def test_a_file_held_in_one_task_is_taken_out_of_it(call, task):
    code = await _on_task(task.code)

    assert (await call("delete", code=f"FILE@{code}"))["result"] is True

    assert await _state(code) == (set(), set(), set(), True)


async def test_a_file_held_in_one_codex_note_is_taken_out_of_it(call, here):
    note = await _codex_note(here.code)
    bound = await codex_file_attach_bytes(note.code, CONTENT, filename="schema.md")

    assert (await call("delete", code=f"FILE@{bound.file_code}"))["result"] is True

    assert await _state(bound.file_code) == (set(), set(), set(), True)


async def test_the_image_word_names_the_same_file(call, task, other_task):
    """``insert`` hands out ``IMAGE@`` for a picture; the agent passes back what it was given."""
    code = await _on_task(task.code)
    await _also_on_task(other_task.code, code)

    assert (
        await call("delete", code=f"IMAGE@{code}", holder=f"TASK@{other_task.code}")
    )["result"] is True
    assert (await call("delete", code=f"image@{code.lower()}"))["result"] is True

    assert await _state(code) == (set(), set(), set(), True)


async def test_one_place_taken_out_leaves_the_task_s_other_files(call, task):
    code = await _on_task(task.code)
    kept = await task_file_attach_bytes(task.code, b"other", filename="other.txt")

    await call("delete", code=f"FILE@{code}")

    assert [row.file_code for row in await task_file_crud.task_file_list(task.code)] == [
        kept.file_code
    ]


# ── several places: the refusal ───────────────────────────────────────────────


async def test_a_file_in_a_task_and_a_codex_note_is_refused_with_both_and_nothing_changes(
    call, task, here
):
    code = await _on_task(task.code)
    note = await _codex_note(here.code)
    await _also_on_note(note.code, code)
    before = await _state(code)

    with pytest.raises(ToolError) as refused:
        await call("delete", code=f"FILE@{code}")

    text = str(refused.value)
    assert "held in 2 places" in text
    assert f"TASK@{task.code} ('Выпуск')" in text
    assert f"CODEX@{note.code} ('Тесты')" in text
    assert "Nothing was taken out" in text
    assert "holder=" in text
    assert await _state(code) == before == (
        {task.code},
        {note.code},
        {Owner("TASK", task.code), Owner("CODEX", note.code)},
        False,
    )


async def test_a_file_in_two_tasks_is_refused_with_both_and_nothing_changes(
    call, task, other_task
):
    code = await _on_task(task.code)
    await _also_on_task(other_task.code, code)
    before = await _state(code)

    with pytest.raises(ToolError, match="held in 2 places") as refused:
        await call("delete", code=f"FILE@{code}")

    assert f"TASK@{task.code}" in str(refused.value)
    assert f"TASK@{other_task.code}" in str(refused.value)
    assert await _state(code) == before
    assert before[0] == {task.code, other_task.code}


# ── the repeat with a holder ──────────────────────────────────────────────────


async def test_the_repeat_with_a_task_takes_it_out_of_that_task_only(call, task, other_task):
    code = await _on_task(task.code)
    await _also_on_task(other_task.code, code)

    assert (await call("delete", code=f"FILE@{code}", holder=f"TASK@{task.code}"))["result"]

    assert await _state(code) == ({other_task.code}, set(), {Owner("TASK", other_task.code)}, False)


async def test_the_repeat_with_a_codex_note_takes_it_out_of_the_note_only(call, task, here):
    code = await _on_task(task.code)
    note = await _codex_note(here.code)
    await _also_on_note(note.code, code)

    assert (await call("delete", code=f"FILE@{code}", holder=f"CODEX@{note.code}"))["result"]

    assert await _state(code) == ({task.code}, set(), {Owner("TASK", task.code)}, False)


async def test_the_repeat_with_the_note_it_was_attached_at_takes_it_out_of_the_task(
    call, task, here
):
    note = await task_note_crud.task_note_add(task_code=task.code, title="Схема")
    code = await _on_task(task.code, place=FilePlace(note_code=note.code))
    codex_note = await _codex_note(here.code)
    await _also_on_note(codex_note.code, code)

    assert (await call("delete", code=f"FILE@{code}", holder=f"NOTE@{note.code}"))["result"]

    kept = Owner("CODEX", codex_note.code)
    assert await _state(code) == (set(), {codex_note.code}, {kept}, False)


async def test_the_repeat_with_the_stage_it_was_attached_at_takes_it_out_of_the_task(
    call, task, other_task
):
    stage = await stage_crud.stage_create(task_code=task.code, title="Сборка")
    code = await _on_task(task.code, place=FilePlace(stage_code=stage.code))
    await _also_on_task(other_task.code, code)

    assert (await call("delete", code=f"FILE@{code}", holder=f"STAGE@{stage.code}"))["result"]

    assert await _state(code) == ({other_task.code}, set(), {Owner("TASK", other_task.code)}, False)
    assert await stage_crud.stage_get(stage.code) is not None


async def test_any_note_of_the_task_names_the_task(call, task, other_task):
    """A file is in a task once: a note names its task, wherever in it the file was attached."""
    note = await task_note_crud.task_note_add(task_code=task.code, title="Схема")
    code = await _on_task(task.code)
    await _also_on_task(other_task.code, code)

    assert (await call("delete", code=f"FILE@{code}", holder=f"NOTE@{note.code}"))["result"]

    assert await _task_holders(code) == {other_task.code}


async def test_a_holder_is_taken_in_any_case(call, task, other_task):
    code = await _on_task(task.code)
    await _also_on_task(other_task.code, code)

    await call("delete", code=f"file@{code.lower()}", holder=f"task@{task.code.lower()}")

    assert await _task_holders(code) == {other_task.code}


async def test_a_holder_names_its_one_place_even_when_it_is_the_only_one(call, task):
    code = await _on_task(task.code)

    assert (await call("delete", code=f"FILE@{code}", holder=f"TASK@{task.code}"))["result"]

    assert await _state(code) == (set(), set(), set(), True)


# ── a holder that does not hold it ────────────────────────────────────────────


async def test_a_task_that_does_not_hold_the_file_is_refused_and_nothing_changes(
    call, task, other_task, here
):
    code = await _on_task(task.code)
    bystander = await task_crud.task_create(workspace_code=here.code, title="Сторонняя")
    await _also_on_task(other_task.code, code)
    before = await _state(code)

    not_held = f"TASK@{bystander.code} does not hold FILE@{code}"
    with pytest.raises(ToolError, match=not_held) as refused:
        await call("delete", code=f"FILE@{code}", holder=f"TASK@{bystander.code}")

    assert f"TASK@{task.code}" in str(refused.value)
    assert await _state(code) == before


async def test_a_codex_note_that_does_not_hold_the_file_is_refused(call, task, here):
    code = await _on_task(task.code)
    note = await _codex_note(here.code)
    before = await _state(code)

    with pytest.raises(ToolError, match=f"CODEX@{note.code} does not hold"):
        await call("delete", code=f"FILE@{code}", holder=f"CODEX@{note.code}")

    assert await _state(code) == before


async def test_a_codex_itself_as_the_holder_is_refused(call, task, here):
    code = await _on_task(task.code)
    note = await _codex_note(here.code)
    await _also_on_note(note.code, code)
    before = await _state(code)

    with pytest.raises(ToolError, match="is a codex, not a note"):
        await call("delete", code=f"FILE@{code}", holder=f"CODEX@{note.codex_code}")

    assert await _state(code) == before


@pytest.mark.parametrize(
    ("holder", "refusal"),
    [
        ("JOURNAL@0000000000", "cannot hold a file"),
        ("WORKSPACE@0000000000", "cannot hold a file"),
        ("python/test", "looks like a codex path"),
        ("TASK@", "is not a TASK@ code"),
        ("TASK@0000000000", "TASK@0000000000 does not exist"),
        ("STAGE@0000000000", "STAGE@0000000000 does not exist"),
        ("NOTE@0000000000", "NOTE@0000000000 does not exist"),
        ("CODEX@0000000000", "CODEX@0000000000 does not exist"),
    ],
)
async def test_a_holder_of_no_place_is_refused_and_nothing_changes(
    call, task, other_task, holder, refusal
):
    code = await _on_task(task.code)
    await _also_on_task(other_task.code, code)
    before = await _state(code)

    with pytest.raises(ToolError, match=refusal):
        await call("delete", code=f"FILE@{code}", holder=holder)

    assert await _state(code) == before


# ── other workspaces and unmounted codexes ────────────────────────────────────


async def test_a_binding_in_another_workspace_is_neither_counted_nor_touched(
    call, task, elsewhere
):
    code = await _on_task(task.code)
    foreign = await task_crud.task_create(workspace_code=elsewhere.code, title="Чужая")
    await _also_on_task(foreign.code, code)

    assert (await call("delete", code=f"FILE@{code}"))["result"] is True

    assert await _state(code) == ({foreign.code}, set(), {Owner("TASK", foreign.code)}, False)


async def test_a_note_of_an_unmounted_codex_is_neither_counted_nor_touched(call, task):
    code = await _on_task(task.code)
    unmounted = await _codex_note(None)
    await _also_on_note(unmounted.code, code)

    assert (await call("delete", code=f"FILE@{code}"))["result"] is True

    assert await _state(code) == (set(), {unmounted.code}, {Owner("CODEX", unmounted.code)}, False)


async def test_a_note_of_a_switched_off_mount_is_neither_counted_nor_touched(call, task, here):
    code = await _on_task(task.code)
    note = await _codex_note(here.code)
    await _also_on_note(note.code, code)
    await mount_crud.mount_remove(note.codex_code, here.code)

    assert (await call("delete", code=f"FILE@{code}"))["result"] is True

    assert await _note_holders(code) == {note.code}


async def test_the_refusal_lists_only_the_places_of_this_workspace(
    call, task, other_task, elsewhere
):
    code = await _on_task(task.code)
    await _also_on_task(other_task.code, code)
    foreign = await task_crud.task_create(workspace_code=elsewhere.code, title="Чужая")
    await _also_on_task(foreign.code, code)

    with pytest.raises(ToolError, match="held in 2 places") as refused:
        await call("delete", code=f"FILE@{code}")

    assert foreign.code not in str(refused.value)
    assert "Чужая" not in str(refused.value)


async def test_a_file_held_only_in_another_workspace_is_refused_and_untouched(
    call, here, elsewhere
):
    foreign = await task_crud.task_create(workspace_code=elsewhere.code, title="Чужая")
    code = await _on_task(foreign.code)
    before = await _state(code)

    with pytest.raises(ToolError, match="is not attached to anything in 'Работа'"):
        await call("delete", code=f"FILE@{code}")

    assert await _state(code) == before


async def test_a_holder_of_another_workspace_is_refused_by_name(call, task, elsewhere):
    code = await _on_task(task.code)
    foreign = await task_crud.task_create(workspace_code=elsewhere.code, title="Чужая")
    await _also_on_task(foreign.code, code)
    before = await _state(code)

    with pytest.raises(ToolError, match="Личное"):
        await call("delete", code=f"FILE@{code}", holder=f"TASK@{foreign.code}")

    assert await _state(code) == before


# ── the holder's write rule ───────────────────────────────────────────────────


async def test_a_read_only_codex_refuses_and_keeps_the_file(call, here):
    note = await _codex_note(here.code, writable=False)
    bound = await codex_file_attach_bytes(note.code, CONTENT, filename="schema.md")
    before = await _state(bound.file_code)

    with pytest.raises(ToolError, match="not editable for you"):
        await call("delete", code=f"FILE@{bound.file_code}")
    with pytest.raises(ToolError, match="not editable for you"):
        await call("delete", code=f"FILE@{bound.file_code}", holder=f"CODEX@{note.code}")

    kept = Owner("CODEX", note.code)
    assert await _state(bound.file_code) == before == (set(), {note.code}, {kept}, False)


async def test_a_read_only_codex_does_not_block_the_task_s_place(call, task, here):
    code = await _on_task(task.code)
    note = await _codex_note(here.code, writable=False)
    await _also_on_note(note.code, code)

    assert (await call("delete", code=f"FILE@{code}", holder=f"TASK@{task.code}"))["result"]

    assert await _state(code) == (set(), {note.code}, {Owner("CODEX", note.code)}, False)


async def test_a_deleted_task_refuses_and_keeps_the_file(call, task):
    code = await _on_task(task.code)
    await task_crud.task_delete(task.code)
    before = await _state(code)

    with pytest.raises(ToolError, match="is deleted"):
        await call("delete", code=f"FILE@{code}")

    assert await _state(code) == before == ({task.code}, set(), {Owner("TASK", task.code)}, False)


async def test_a_deleted_task_is_listed_as_deleted(call, task, other_task):
    code = await _on_task(task.code)
    await _also_on_task(other_task.code, code)
    await task_crud.task_delete(task.code)

    with pytest.raises(ToolError, match=f"TASK@{task.code} \\('Выпуск', deleted\\)"):
        await call("delete", code=f"FILE@{code}")


# ── codes that name no file ───────────────────────────────────────────────────


@pytest.mark.parametrize("code", ["FILE@0000000000", "FILE@ZZZZ", "FILE@00000000000000"])
async def test_a_file_code_of_nothing_deletes_nothing(call, task, code):
    kept = await _on_task(task.code)

    assert (await call("delete", code=code))["result"] is False

    assert await _task_holders(kept) == {task.code}


async def test_a_truncated_file_code_is_refused(call, task):
    with pytest.raises(ToolError, match="is not a FILE@ code"):
        await call("delete", code="FILE@")


async def test_a_holder_on_anything_but_a_file_is_refused_and_deletes_nothing(call, task):
    with pytest.raises(ToolError, match="`holder` names the place to take a file out of"):
        await call("delete", code=f"TASK@{task.code}", holder=f"TASK@{task.code}")

    assert await task_crud.task_get(task.code) is not None


async def test_an_empty_holder_is_no_holder(call, task):
    code = await _on_task(task.code)

    assert (await call("delete", code=f"FILE@{code}", holder=""))["result"] is True

    assert await _task_holders(code) == set()
