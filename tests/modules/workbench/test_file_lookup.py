"""``FILE@`` and ``IMAGE@`` in the lookup: one file under two words, answered under the one asked.

A file is shown wherever it was brought in: the miss is the storage's own — no stored file, one
outside the served store or without its bytes — ``not_found``; the file deleted or let go by its
last holder — ``deleted``. The title is the binding's visible in the filter's workspace, else the
name the file came under there, else the neutral ``<CODE><ext>`` — never a name from another
workspace. A batch costs a fixed number of statements.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from sqlalchemy import event

from src.core.config import Config
from src.core.database.runtime import get_engine
from src.modules.codex import files as codex_files
from src.modules.codex.crud import codex as codex_crud
from src.modules.codex.crud import mount as mount_crud
from src.modules.codex.crud import note as codex_note_crud
from src.modules.core_lookup import engine
from src.modules.core_storage.dto import Owner
from src.modules.core_storage.services.files import file_delete, file_get, file_path
from src.modules.core_storage.services.registration import file_register_bytes
from src.modules.tasks import files as task_files
from src.modules.tasks.crud import task as task_crud
from src.modules.workbench.module import WorkbenchModule
from src.modules.workspace.crud.workspace import workspace_create
from tests.modules.codex.file_support import codex_file_attach_bytes
from tests.modules.tasks.file_support import task_file_attach_bytes

pytestmark = pytest.mark.db

PNG = bytes.fromhex("89504e470d0a1a0a0000000d49484452") + b"\x00" * 64


@pytest.fixture
def registered(config: Config) -> None:
    WorkbenchModule().configure(FastAPI(), config)


@pytest.fixture
async def here(workspace, storage, registered):
    return workspace


@pytest.fixture
async def there(db):
    return await workspace_create(title="Личное")


@pytest.fixture
async def task(here):
    return await task_crud.task_create(workspace_code=here.code, title="Выпуск")


async def _preview(
    codes: list[str], workspace: str | None, holder: str | None = None
) -> dict[str, dict]:
    filters = {"workspace": f"WORKSPACE@{workspace}"} if workspace else {}
    if holder:
        filters["holder"] = holder
    return {record.code: record.model_dump() for record in await engine.preview(codes, filters)}


def _miss(record: dict) -> str | None:
    return record["error"]["code"] if record["error"] else None


def _neutral(file_code: str) -> dict:
    """Shown, and called by nothing but its code: what a workspace with no place of it sees. The type
    is the file's own, not a name given somewhere: it is told here too."""
    return {
        "title": f"{file_code}.png",
        "description": "",
        "link": f"/storage/public/{file_code}",
        "mime": "image/png",
        "held": False,
        "error": None,
    }


def _without_code(record: dict) -> dict:
    return {key: value for key, value in record.items() if key != "code"}


async def _codex_note(workspace_code: str | None, segment: str = "python"):
    codex = await codex_crud.codex_create(segment=segment, title=segment.title())
    if workspace_code is not None:
        await mount_crud.mount_add(codex.code, workspace_code)
    return await codex_note_crud.note_create(parent_code=codex.code, segment="test", title="Тесты")


async def test_both_words_answer_under_the_word_asked(task, here):
    bound = await task_file_attach_bytes(
        task.code, PNG, filename="shot.png", title="Экран", description="вход"
    )
    code = bound.file_code

    got = await _preview([f"FILE@{code}", f"image@{code.lower()}"], here.code)

    expected = {
        "title": "Экран",
        "description": "вход",
        "link": f"/storage/public/{code}",
        "mime": "image/png",
        "held": False,
        "error": None,
    }
    assert got[f"FILE@{code}"] == {"code": f"FILE@{code}", **expected}
    assert got[f"IMAGE@{code}"] == {"code": f"IMAGE@{code}", **expected}


async def test_without_a_workspace_the_file_is_called_by_its_code_only(task, here):
    """No workspace in the filter, no boundary to see a place through: the title, the description
    and the name a file came under anywhere stay where they were given."""
    bound = await task_file_attach_bytes(
        task.code, PNG, filename="secret-plan.png", title="Только здесь", description="внутри"
    )
    code = f"FILE@{bound.file_code}"

    got = await _preview([code], None)

    assert _without_code(got[code]) == _neutral(bound.file_code)
    assert _without_code((await _preview([code], None, f"TASK@{task.code}"))[code]) == _neutral(
        bound.file_code
    )


async def test_the_type_is_the_files_own_and_names_its_glyph(task, here):
    """The pill picks its glyph by the stored file's type — a PDF is a PDF whatever the holder
    called it, and in a workspace that sees no place of it as well; a task's code has no type."""
    pdf = await task_file_attach_bytes(
        task.code, b"%PDF-1.4\n" + b"\x00" * 64, filename="report.pdf", title="Отчёт без расширения"
    )
    code = f"FILE@{pdf.file_code}"

    assert (await _preview([code], here.code))[code]["mime"] == "application/pdf"
    assert (await _preview([code], None))[code]["mime"] == "application/pdf"
    assert (await _preview([f"TASK@{task.code}"], here.code))[f"TASK@{task.code}"]["mime"] == ""


async def test_the_link_opens_the_file_and_names_no_holder(task, here):
    """The address only opens the file: whichever page asks, it carries no holder and no name."""
    note = await _codex_note(here.code)
    bound = await task_file_attach_bytes(task.code, PNG, filename="t.png", title="Из задачи")
    await codex_files.codex_file_attach_existing(note.code, bound.file_code, title="Из заметки")
    code = f"FILE@{bound.file_code}"

    by_task = await _preview([code], here.code, f"TASK@{task.code}")
    by_note = await _preview([code], here.code, f"CODEX@{note.code}")

    assert by_task[code]["link"] == f"/storage/public/{bound.file_code}"
    assert by_note[code]["link"] == f"/storage/public/{bound.file_code}"
    assert by_task[code]["title"] == "Из задачи"
    assert by_note[code]["title"] == "Из заметки"


async def test_held_only_where_the_pages_own_holder_binds_the_file(task, here):
    """The page may edit a file's title only where the title is its own holder's."""
    other = await task_crud.task_create(workspace_code=here.code, title="Соседняя")
    bound = await task_file_attach_bytes(task.code, PNG, filename="t.png", title="Из задачи")
    code = f"IMAGE@{bound.file_code}"

    assert (await _preview([code], here.code, f"TASK@{task.code}"))[code]["held"] is True
    shown_elsewhere = (await _preview([code], here.code, f"TASK@{other.code}"))[code]
    assert (shown_elsewhere["title"], shown_elsewhere["held"]) == ("Из задачи", False)
    assert (await _preview([code], here.code))[code]["held"] is False


async def test_an_untitled_file_is_called_by_the_name_it_came_under_there(task, here, there):
    foreign = await task_crud.task_create(workspace_code=there.code, title="Чужая")
    bound = await task_file_attach_bytes(foreign.code, PNG, filename="чужой.png")
    await task_files.task_file_attach_existing(task.code, bound.file_code, filename="Shot.PNG")

    got = await _preview([f"FILE@{bound.file_code}"], here.code)

    assert got[f"FILE@{bound.file_code}"]["title"] == "Shot.PNG"


async def test_a_titled_binding_is_preferred_to_an_untitled_one(task, here):
    other = await task_crud.task_create(workspace_code=here.code, title="Отчёт")
    bound = await task_file_attach_bytes(task.code, PNG, filename="shot.png")
    await task_files.task_file_attach_existing(other.code, bound.file_code, title="Главный экран")

    got = await _preview([f"FILE@{bound.file_code}"], here.code)

    assert got[f"FILE@{bound.file_code}"]["title"] == "Главный экран"


async def test_the_page_s_own_holder_names_the_file_as_its_files_panel_does(task, here):
    """On a task's page the text says what the task's files panel says, even when another task
    of the workspace gave the same file a title."""
    other = await task_crud.task_create(workspace_code=here.code, title="Отчёт")
    bound = await task_file_attach_bytes(other.code, PNG, filename="w.png", title="5. Отчёт")
    await task_files.task_file_attach_existing(task.code, bound.file_code, filename="Отчёт за неделю.png")
    code = f"IMAGE@{bound.file_code}"

    assert (await _preview([code], here.code))[code]["title"] == "5. Отчёт"
    assert (await _preview([code], here.code, f"TASK@{task.code}"))[code]["title"] == "Отчёт за неделю.png"
    assert (await _preview([code], here.code, f"task@{other.code.lower()}"))[code]["title"] == "5. Отчёт"


async def test_a_codex_note_page_names_the_file_by_its_own_binding(task, here):
    note = await _codex_note(here.code)
    bound = await task_file_attach_bytes(task.code, PNG, filename="t.png", title="Из задачи")
    await codex_files.codex_file_attach_existing(note.code, bound.file_code, title="Из заметки")
    code = f"FILE@{bound.file_code}"

    assert (await _preview([code], here.code, f"CODEX@{note.code}"))[code]["title"] == "Из заметки"


async def test_a_holder_of_another_workspace_names_nothing_here(task, here, there):
    foreign = await task_crud.task_create(workspace_code=there.code, title="Чужая")
    bound = await task_file_attach_bytes(foreign.code, PNG, filename="x.png", title="Тайна")
    code = f"FILE@{bound.file_code}"

    got = (await _preview([code], here.code, f"TASK@{foreign.code}"))[code]

    assert _without_code(got) == _neutral(bound.file_code)


async def test_a_file_with_no_name_anywhere_is_called_by_its_code(task, here):
    bound = await task_file_attach_bytes(task.code, PNG)

    got = await _preview([f"FILE@{bound.file_code}"], here.code)

    assert got[f"FILE@{bound.file_code}"]["title"] == f"{bound.file_code}.png"


async def test_a_codex_note_s_file_is_named_where_the_codex_is_mounted(here, there):
    note = await _codex_note(here.code)
    bound = await codex_file_attach_bytes(
        note.code, PNG, filename="flow.png", title="Поток"
    )
    code = f"FILE@{bound.file_code}"

    assert (await _preview([code], here.code))[code]["title"] == "Поток"
    assert _without_code((await _preview([code], there.code))[code]) == _neutral(bound.file_code)


async def test_a_switched_off_mount_shows_the_file_by_its_code(here):
    note = await _codex_note(here.code)
    bound = await codex_file_attach_bytes(note.code, PNG, filename="flow.png")
    await mount_crud.mount_remove(note.codex_code, here.code)
    code = f"FILE@{bound.file_code}"

    assert _without_code((await _preview([code], here.code))[code]) == _neutral(bound.file_code)


async def test_a_deleted_codex_still_mounted_names_nothing_here(here):
    """The tools see no place in a deleted codex (``mount_get``); the preview names none either.
    The codex's note still holds the file, so it is shown."""
    note = await _codex_note(here.code)
    bound = await codex_file_attach_bytes(note.code, PNG, filename="flow.png")
    await codex_crud.codex_delete(note.codex_code)
    code = f"FILE@{bound.file_code}"

    assert _without_code((await _preview([code], here.code))[code]) == _neutral(bound.file_code)
    assert _without_code((await _preview([code], None))[code]) == _neutral(bound.file_code)


async def test_a_file_of_another_workspace_is_shown_without_its_name_there(here, there):
    foreign = await task_crud.task_create(workspace_code=there.code, title="Чужая")
    bound = await task_file_attach_bytes(
        foreign.code, PNG, filename="acme-contract.png", title="Договор", description="тайна"
    )
    code = f"IMAGE@{bound.file_code}"

    assert _without_code((await _preview([code], here.code))[code]) == _neutral(bound.file_code)
    assert (await _preview([code], there.code))[code]["title"] == "Договор"
    assert _without_code((await _preview([code], None))[code]) == _neutral(bound.file_code)


async def test_a_live_file_no_holder_binds_is_shown_by_its_code(here):
    """An owner the binding tables do not know — another consumer of the storage, or one left
    behind by a failed release — still has its file served, so the text shows it."""
    stored = await file_register_bytes(
        PNG, store="public", owner=Owner("elsewhere.thing", "x1"), filename="secret.png"
    )
    code = f"FILE@{stored.code}"

    assert _without_code((await _preview([code], here.code))[code]) == _neutral(stored.code)


@pytest.mark.parametrize("code", ["FILE@0000000000", "IMAGE@0000000000", "FILE@ZZZZZZZZZZ"])
async def test_no_such_file_is_not_found(here, code):
    assert _miss((await _preview([code], here.code))[code.upper()]) == "not_found"


async def test_a_file_outside_the_served_store_is_not_found(here):
    stored = await file_register_bytes(
        PNG, store="private", owner=Owner("elsewhere.thing", "x1"), filename="key.png"
    )
    code = f"FILE@{stored.code}"

    assert _miss((await _preview([code], here.code))[code]) == "not_found"
    assert _miss((await _preview([code], None))[code]) == "not_found"


async def test_a_file_whose_bytes_are_gone_is_not_found(task, here):
    bound = await task_file_attach_bytes(task.code, PNG, filename="shot.png")
    file_path(await file_get(bound.file_code)).unlink()
    code = f"FILE@{bound.file_code}"

    assert _miss((await _preview([code], here.code))[code]) == "not_found"


async def test_a_file_its_last_holder_let_go_is_deleted(task, here):
    bound = await task_file_attach_bytes(task.code, PNG, filename="shot.png")
    await task_files.task_file_detach(task.code, bound.file_code)
    code = f"FILE@{bound.file_code}"

    assert _miss((await _preview([code], here.code))[code]) == "deleted"


async def test_a_file_the_file_manager_deleted_is_deleted(task, here, there):
    bound = await task_file_attach_bytes(task.code, PNG, filename="shot.png")
    await file_delete(bound.file_code)
    code = f"FILE@{bound.file_code}"

    assert _miss((await _preview([code], here.code))[code]) == "deleted"
    assert _miss((await _preview([code], there.code))[code]) == "deleted"


async def test_a_file_of_a_task_in_the_trash_is_still_shown(task, here):
    """The trash keeps its task's files — restoring brings them back whole — and the storage
    serves them meanwhile."""
    bound = await task_file_attach_bytes(task.code, PNG, filename="shot.png")
    await task_crud.task_delete(task.code)
    code = f"FILE@{bound.file_code}"

    got = (await _preview([code], here.code))[code]

    assert got["error"] is None
    assert got["title"] == "shot.png"


async def test_one_live_holder_keeps_the_file_alive(task, here):
    other = await task_crud.task_create(workspace_code=here.code, title="Отчёт")
    bound = await task_file_attach_bytes(
        task.code, PNG, filename="shot.png", title="Старый"
    )
    await task_files.task_file_attach_existing(other.code, bound.file_code, title="Новый")
    await task_crud.task_delete(task.code)
    code = f"FILE@{bound.file_code}"

    assert (await _preview([code], here.code))[code]["title"] == "Новый"


async def test_a_trashed_holder_in_another_workspace_tells_nothing_here(here, there):
    foreign = await task_crud.task_create(workspace_code=there.code, title="Чужая")
    bound = await task_file_attach_bytes(foreign.code, PNG, filename="shot.png")
    await task_crud.task_delete(foreign.code)
    code = f"FILE@{bound.file_code}"

    assert _without_code((await _preview([code], here.code))[code]) == _neutral(bound.file_code)


async def test_the_sql_count_does_not_grow_with_the_batch(here):
    note = await _codex_note(here.code)
    tasks = [
        await task_crud.task_create(workspace_code=here.code, title=f"Задача {n}") for n in range(6)
    ]
    codes = []
    for n, holder in enumerate(tasks):
        bound = await task_file_attach_bytes(
            holder.code, PNG + bytes([n]), filename=f"shot{n}.png", title="" if n % 2 else "Экран"
        )
        await codex_files.codex_file_attach_existing(note.code, bound.file_code)
        codes += [f"FILE@{bound.file_code}", f"IMAGE@{bound.file_code}"]

    async def statements(batch: list[str]) -> int:
        seen: list[str] = []

        def count(conn, cursor, statement, *args):
            if statement.lstrip().upper().startswith("SELECT"):
                seen.append(statement)

        sync_engine = get_engine().sync_engine
        event.listen(sync_engine, "before_cursor_execute", count)
        try:
            await _preview(batch, here.code)
        finally:
            event.remove(sync_engine, "before_cursor_execute", count)
        return len(seen)

    one = await statements([codes[0], codes[1]])
    many = await statements(codes)
    answered = await _preview(codes, here.code)

    assert 0 < one == many
    assert [code for code, record in answered.items() if record["error"]] == []
    assert answered[codes[2]]["title"] == "shot1.png"
