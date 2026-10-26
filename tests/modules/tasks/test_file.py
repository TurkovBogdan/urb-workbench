"""Files of a task through the service: attach, re-title, reorder, detach — and every refusal.

A file from bytes goes the uploads' way — spooled, then ``task_file_attach_spooled``
(``file_support.py``); taking a path or a request body is ``core_storage_upload``'s and is tested
there.

The storage is real (``storage`` fixture, a temp folder): what a test asserts is the state after
the call — the binding rows and the storage owners — not the text of an answer. Attaching writes
in two transactions, so a refusal is checked by reading both sides back: the binding absent, and
no owner left behind (or, where the task did hold the file, the owner still live).
"""

from __future__ import annotations

import pytest
from sqlalchemy import func, select

from src.core.database import session_scope
from src.modules.core_storage.dto import Owner
from src.modules.core_storage.errors import FileTooLarge
from src.modules.core_storage.models import CoreStorageFile
from src.modules.core_storage.services.files import file_delete, file_get
from src.modules.core_storage.services.ownership import file_owners
from src.modules.core_storage.services.registration import file_register_bytes
from src.modules.tasks import files as task_files
from src.modules.tasks.constants import FILE_TITLE_MAX, SORT_DEFAULT, SORT_STEP, TYPE_EXTENDED
from src.modules.tasks.crud import file as file_crud
from src.modules.tasks.crud.note import task_note_add
from src.modules.tasks.crud.stage import stage_create
from src.modules.tasks.crud.task import task_create, task_delete
from src.modules.tasks.errors import (
    FILE_ALREADY_ATTACHED,
    FILE_FOREIGN_PLACE,
    FILE_FOREIGN_STORE,
    FILE_NOT_FOUND,
    FILE_NOT_STORED,
    TASK_DELETED,
    TaskRuleError,
)
from src.modules.tasks.files import FilePlace
from tests.modules.tasks.file_support import task_file_attach_bytes

pytestmark = pytest.mark.db

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64


async def _task(workspace, title: str = "Выпуск"):
    return await task_create(workspace_code=workspace.code, title=title, type=TYPE_EXTENDED)


async def _stored_count() -> int:
    async with session_scope() as s:
        return (await s.execute(select(func.count()).select_from(CoreStorageFile))).scalar_one()


async def _live_owners(code: str) -> list[Owner]:
    return [place.owner for place in await file_owners(code)]


def _owner(task) -> Owner:
    return Owner(type="TASK", id=task.code)


# ── attach ────────────────────────────────────────────────────────────────────


async def test_attach_stores_the_file_and_binds_it_at_the_end(workspace, storage):
    task = await _task(workspace)

    first = await task_file_attach_bytes(task.code, PNG, filename="screen.PNG")
    second = await task_file_attach_bytes(
        task.code, b"# notes\n", filename="notes.md", title="Заметки к релизу"
    )

    assert (first.sort, second.sort) == (SORT_DEFAULT, SORT_DEFAULT - SORT_STEP)
    assert [row.file_code for row in await file_crud.task_file_list(task.code)] == [
        first.file_code,
        second.file_code,
    ]
    assert await _live_owners(first.file_code) == [_owner(task)]
    names = {p.owner: (p.original_filename, p.original_extension) for p in await file_owners(first.file_code)}
    assert names[_owner(task)] == ("screen", ".PNG")
    assert (await file_get(first.file_code)).store == "public"
    views = await task_files.task_file_views(task.code)
    assert [(v.binding.title, v.original_filename, v.stored.type) for v in views] == [
        ("", "screen", "image"),
        ("Заметки к релизу", "notes", "text"),
    ]


async def test_attach_to_a_note_and_to_a_stage_of_the_task(workspace, storage):
    task = await _task(workspace)
    note = await task_note_add(task_code=task.code, title="Схема")
    stage = await stage_create(task_code=task.code, title="Сборка")

    on_note = await task_file_attach_bytes(
        task.code, b"a", filename="a.txt", place=FilePlace(note_code=note.code)
    )
    on_stage = await task_file_attach_bytes(
        task.code, b"b", filename="b.txt", place=FilePlace(stage_code=stage.code)
    )

    assert (on_note.note_code, on_note.stage_code) == (note.code, None)
    assert (on_stage.note_code, on_stage.stage_code) == (None, stage.code)
    # The storage sees the task as the owner: notes and stages are places inside it.
    assert await _live_owners(on_note.file_code) == [_owner(task)]
    assert await _live_owners(on_stage.file_code) == [_owner(task)]


@pytest.mark.parametrize("where", ["note", "stage", "both"])
async def test_a_place_not_of_this_task_is_refused_and_nothing_is_stored(workspace, storage, where):
    task, other = await _task(workspace), await _task(workspace, "Чужая")
    note = await task_note_add(task_code=other.code, title="Чужая заметка")
    stage = await stage_create(task_code=other.code, title="Чужой этап")
    own_note = await task_note_add(task_code=task.code, title="Своя")
    own_stage = await stage_create(task_code=task.code, title="Свой")
    place = {
        "note": FilePlace(note_code=note.code),
        "stage": FilePlace(stage_code=stage.code),
        "both": FilePlace(note_code=own_note.code, stage_code=own_stage.code),
    }[where]

    with pytest.raises(TaskRuleError) as refused:
        await task_file_attach_bytes(task.code, PNG, filename="x.png", place=place)

    assert refused.value.code == FILE_FOREIGN_PLACE
    assert await file_crud.task_file_list(task.code) == []
    assert await _stored_count() == 0


async def test_a_deleted_note_is_no_place_for_a_file(workspace, storage):
    from src.modules.notes.crud import note as notes_crud

    task = await _task(workspace)
    note = await task_note_add(task_code=task.code, title="Удалю")
    await notes_crud.note_delete(note.code)

    with pytest.raises(TaskRuleError) as refused:
        await task_file_attach_bytes(
            task.code, PNG, filename="x.png", place=FilePlace(note_code=note.code)
        )

    assert refused.value.code == FILE_FOREIGN_PLACE
    assert await _stored_count() == 0


async def test_a_deleted_task_takes_no_file_and_nothing_is_stored(workspace, storage):
    task = await _task(workspace)
    await task_delete(task.code)

    with pytest.raises(TaskRuleError) as refused:
        await task_file_attach_bytes(task.code, PNG, filename="x.png")

    assert refused.value.code == TASK_DELETED
    assert await _stored_count() == 0


async def test_a_title_over_the_limit_is_refused_before_the_storage(workspace, storage):
    task = await _task(workspace)

    with pytest.raises(ValueError, match=str(FILE_TITLE_MAX)):
        await task_file_attach_bytes(
            task.code, PNG, filename="x.png", title="т" * (FILE_TITLE_MAX + 1)
        )

    assert await _stored_count() == 0


@pytest.mark.parametrize(
    ("field", "value"),
    [("title", "Вход\x00"), ("title", "Вход\tэкран"), ("description", "после\x07входа")],
)
async def test_a_control_character_is_refused_by_the_service_before_the_storage(
    workspace, storage, field, value
):
    """The rule lives in the service, so every surface — HTTP, the agent, an upload slot — meets
    the same refusal, with the field named."""
    from src.modules.tasks.errors import FILE_CONTROL_CHARACTER

    task = await _task(workspace)

    with pytest.raises(TaskRuleError) as refused:
        await task_file_attach_bytes(task.code, PNG, filename="x.png", **{field: value})

    assert refused.value.code == FILE_CONTROL_CHARACTER
    assert refused.value.params == {"field": field}
    assert await _stored_count() == 0
    assert await file_crud.task_file_list(task.code) == []


async def test_a_retitle_with_a_control_character_changes_nothing(workspace, storage):
    from src.modules.tasks.errors import FILE_CONTROL_CHARACTER

    task = await _task(workspace)
    bound = await task_file_attach_bytes(task.code, PNG, filename="x.png", title="Было")

    with pytest.raises(TaskRuleError) as refused:
        await task_files.task_file_retitle(task.code, bound.file_code, description="a\x00b")

    assert refused.value.code == FILE_CONTROL_CHARACTER
    row = await file_crud.task_file_get(task.code, bound.file_code)
    assert (row.title, row.description) == ("Было", "")


async def test_a_storage_refusal_writes_no_binding(workspace, storage, monkeypatch):
    monkeypatch.setattr("src.modules.core_storage.services.registration.max_file_size", lambda: 4)
    task = await _task(workspace)

    with pytest.raises(FileTooLarge):
        await task_file_attach_bytes(task.code, PNG, filename="x.png")

    assert await file_crud.task_file_list(task.code) == []
    assert await _stored_count() == 0


async def test_one_file_in_two_tasks_has_two_owners(workspace, storage):
    first, second = await _task(workspace), await _task(workspace, "Вторая")
    bound = await task_file_attach_bytes(first.code, PNG, filename="screen.png")

    again = await task_files.task_file_attach_existing(second.code, bound.file_code)

    assert again.file_code == bound.file_code
    assert sorted(await _live_owners(bound.file_code), key=lambda o: o.id) == sorted(
        [_owner(first), _owner(second)], key=lambda o: o.id
    )
    names = {p.owner: p.original_filename for p in await file_owners(bound.file_code)}
    # Attached by its code, the file keeps the name it came in with elsewhere.
    assert names[_owner(second)] == "screen"


async def test_the_same_content_twice_is_one_file_and_the_second_attach_is_refused(
    workspace, storage
):
    task = await _task(workspace)
    bound = await task_file_attach_bytes(task.code, PNG, filename="screen.png")

    with pytest.raises(TaskRuleError) as refused:
        await task_file_attach_bytes(task.code, PNG, filename="copy.png")

    assert refused.value.code == FILE_ALREADY_ATTACHED
    # The storage deduplicated into the bound file, and the refusal must not release the owner
    # the binding stands on.
    assert [row.file_code for row in await file_crud.task_file_list(task.code)] == [bound.file_code]
    assert await _live_owners(bound.file_code) == [_owner(task)]
    assert (await file_get(bound.file_code)).deleted_at is None
    # A refusal writes nothing — the place keeps the name the file came under first.
    names = {p.owner: (p.original_filename, p.original_extension) for p in await file_owners(bound.file_code)}
    assert names == {_owner(task): ("screen", ".png")}


async def test_the_same_content_after_the_file_manager_deleted_it_brings_the_binding_back(
    workspace, storage
):
    """The file manager's deletion hides the file and keeps the binding row; the same bytes
    again revive the file and the place, and the answer is the binding that is back."""
    task = await _task(workspace)
    bound = await task_file_attach_bytes(
        task.code, PNG, filename="screen.png", title="Экран"
    )
    await file_delete(bound.file_code)
    assert await task_files.task_file_views(task.code) == []

    back = await task_file_attach_bytes(task.code, PNG, filename="again.png", title="Новый")

    assert (back.file_code, back.title) == (bound.file_code, "Экран")
    assert [view.binding.file_code for view in await task_files.task_file_views(task.code)] == [
        bound.file_code
    ]
    assert await _live_owners(bound.file_code) == [_owner(task)]
    assert (await file_get(bound.file_code)).deleted_at is None


async def test_attaching_a_file_the_task_holds_by_its_code_writes_nothing(workspace, storage):
    task = await _task(workspace)
    bound = await task_file_attach_bytes(task.code, PNG, filename="screen.png")

    with pytest.raises(TaskRuleError) as refused:
        await task_files.task_file_attach_existing(task.code, bound.file_code, filename="other.png")

    assert refused.value.code == FILE_ALREADY_ATTACHED
    names = {p.owner: p.original_filename for p in await file_owners(bound.file_code)}
    assert names == {_owner(task): "screen"}


async def test_attaching_an_unknown_code_is_refused(workspace, storage):
    task = await _task(workspace)

    with pytest.raises(TaskRuleError) as refused:
        await task_files.task_file_attach_existing(task.code, "ABCDEF0123")

    assert refused.value.code == FILE_NOT_STORED
    assert await file_crud.task_file_list(task.code) == []


async def test_a_file_of_another_store_is_refused_and_nothing_is_written(workspace, storage):
    """A task's files are served from ``public``; a ``private`` file bound here would be listed
    and never open."""
    task = await _task(workspace)
    private = await file_register_bytes(b"secret", store="private", owner=Owner("other", "1"))

    with pytest.raises(TaskRuleError) as refused:
        await task_files.task_file_attach_existing(task.code, private.code)

    assert refused.value.code == FILE_FOREIGN_STORE
    assert await file_crud.task_file_list(task.code) == []
    assert await _live_owners(private.code) == [Owner("other", "1")]


async def test_a_binding_refused_after_the_storage_gives_the_owner_back(
    workspace, storage, monkeypatch
):
    task = await _task(workspace)

    async def refuse(**_):
        raise TaskRuleError(TASK_DELETED, "deleted meanwhile")

    monkeypatch.setattr(file_crud, "task_file_create", refuse)

    with pytest.raises(TaskRuleError):
        await task_file_attach_bytes(task.code, PNG, filename="x.png")

    async with session_scope() as s:
        stored = (await s.execute(select(CoreStorageFile))).scalars().all()
    assert len(stored) == 1
    assert await _live_owners(stored[0].code) == []
    assert stored[0].deleted_at is not None


async def test_a_spooled_file_keeps_the_name_it_came_under(workspace, storage):
    task = await _task(workspace)

    pdf = await task_file_attach_bytes(task.code, b"%PDF-1.4 body", filename="report.final.pdf")
    log = await task_file_attach_bytes(task.code, b"log line 1\n", filename="run.log")

    names = {
        v.binding.file_code: (v.original_filename, v.original_extension)
        for v in await task_files.task_file_views(task.code)
    }
    assert names == {pdf.file_code: ("report.final", ".pdf"), log.file_code: ("run", ".log")}
    assert [path for path in storage.tmp.rglob("*") if path.is_file()] == []


async def test_an_upload_is_hashed_once(workspace, storage, monkeypatch):
    """The spool counts the bytes as they arrive; the registration takes those counts and does not
    read the file again."""
    import hashlib
    from types import SimpleNamespace

    from src.modules.core_storage.services import registration

    made: list[object] = []

    def counted(*args):
        digest = hashlib.sha256(*args)
        made.append(digest)
        return digest

    monkeypatch.setattr(registration, "hashlib", SimpleNamespace(sha256=counted))
    task = await _task(workspace)

    bound = await task_file_attach_bytes(
        task.code, b"line 1\n" * 1000 + b"line 2\n" * 1000, filename="run.log"
    )

    assert len(made) == 1
    stored = await file_get(bound.file_code)
    assert stored.sha256 == hashlib.sha256(b"line 1\n" * 1000 + b"line 2\n" * 1000).hexdigest()
    assert stored.size == 14000


async def test_the_files_list_costs_the_same_statements_for_any_number_of_files(workspace, storage):
    from sqlalchemy import event

    from src.core.database import get_engine

    few, many = await _task(workspace), await _task(workspace, "Много")
    for n in range(2):
        await task_file_attach_bytes(few.code, PNG + bytes([n]), filename=f"{n}.png")
    for n in range(12):
        await task_file_attach_bytes(many.code, PNG + bytes([100 + n]), filename=f"{n}.png")

    async def statements(task_code: str) -> tuple[int, int]:
        seen: list[str] = []

        def count(conn, cursor, statement, *args):
            seen.append(statement)

        sync_engine = get_engine().sync_engine
        event.listen(sync_engine, "before_cursor_execute", count)
        try:
            views = await task_files.task_file_views(task_code)
        finally:
            event.remove(sync_engine, "before_cursor_execute", count)
        return len(seen), len(views)

    few_statements, few_views = await statements(few.code)
    many_statements, many_views = await statements(many.code)

    assert (few_views, many_views) == (2, 12)
    assert few_statements == many_statements
    names = [view.original_filename for view in await task_files.task_file_views(many.code)]
    assert names == [str(n) for n in range(12)]


# ── edit, order, detach ───────────────────────────────────────────────────────


async def test_title_and_description_change_without_moving_the_file(workspace, storage):
    task = await _task(workspace)
    first = await task_file_attach_bytes(task.code, b"1", filename="1.txt")
    await task_file_attach_bytes(task.code, b"2", filename="2.txt")

    row = await file_crud.task_file_update(task.code, first.file_code, title="Лог", description="Что внутри")
    cleared = await file_crud.task_file_update(task.code, first.file_code, title="")

    assert (row.title, row.description, row.sort) == ("Лог", "Что внутри", first.sort)
    assert (cleared.title, cleared.description) == ("", "Что внутри")
    assert await file_crud.task_file_update(task.code, "0000000000", title="x") is None


async def test_reorder_takes_the_whole_order_and_refuses_a_foreign_code(workspace, storage):
    task = await _task(workspace)
    codes = [
        (await task_file_attach_bytes(task.code, bytes([n]), filename=f"{n}.txt")).file_code
        for n in range(3)
    ]

    await file_crud.task_file_reorder(task.code, [codes[2], codes[0]])
    order = [row.file_code for row in await file_crud.task_file_list(task.code)]
    sorts = [row.sort for row in await file_crud.task_file_list(task.code)]

    assert order == [codes[2], codes[0], codes[1]]
    # Renumbered by the step from the top, as the task notes are: the named ones, then the rest.
    assert sorts == [SORT_DEFAULT + SORT_STEP, SORT_DEFAULT, SORT_DEFAULT - SORT_STEP]

    with pytest.raises(TaskRuleError) as refused:
        await file_crud.task_file_reorder(task.code, [codes[1], "0000000000"])
    assert refused.value.code == FILE_NOT_FOUND
    assert [row.file_code for row in await file_crud.task_file_list(task.code)] == order


async def test_detach_removes_the_row_and_releases_the_owner(workspace, storage):
    task, other = await _task(workspace), await _task(workspace, "Вторая")
    bound = await task_file_attach_bytes(task.code, PNG, filename="x.png")
    shared = await task_file_attach_bytes(task.code, b"shared", filename="s.txt")
    await task_files.task_file_attach_existing(other.code, shared.file_code)

    assert await task_files.task_file_detach(task.code, bound.file_code) is True
    assert await task_files.task_file_detach(task.code, shared.file_code) is True
    assert await task_files.task_file_detach(task.code, bound.file_code) is False

    assert await file_crud.task_file_list(task.code) == []
    assert await _live_owners(bound.file_code) == []
    assert (await file_get(bound.file_code, include_deleted=True)).deleted_at is not None
    # A file another task still holds stays.
    assert await _live_owners(shared.file_code) == [_owner(other)]
    assert (await file_get(shared.file_code)).deleted_at is None


async def test_where_a_file_is_bound(workspace, storage):
    first, second = await _task(workspace), await _task(workspace, "Вторая")
    bound = await task_file_attach_bytes(first.code, PNG, filename="x.png")
    await task_files.task_file_attach_existing(second.code, bound.file_code)

    holders = await file_crud.task_file_list_by_file(bound.file_code)

    assert {row.task_code for row in holders} == {first.code, second.code}
