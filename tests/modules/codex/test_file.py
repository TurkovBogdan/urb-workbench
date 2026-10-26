"""Files of a codex note through the service, and what each deletion does to them in the storage.

The holder is a note, never a codex — their codes share ``CODEX@``. A soft deletion of a note or a
codex keeps the files for a restore; the CRUD's hard deletions (no surface reaches them) still
release the storage owners. Every test reads the binding rows and the storage owners back. A file
from bytes goes the uploads' way — spooled, then ``codex_file_attach_spooled``
(``file_support.py``).
"""

from __future__ import annotations

import asyncio

import pytest
from sqlalchemy import func, select

from src.core.database import session_scope
from src.modules.codex import files as codex_files
from src.modules.codex.constants import SORT_DEFAULT, SORT_STEP
from src.modules.codex.crud import codex as codex_crud
from src.modules.codex.crud import file as file_crud
from src.modules.codex.crud import note as note_crud
from src.modules.codex.errors import (
    CODEX_DELETED,
    FILE_ALREADY_ATTACHED,
    FILE_FOREIGN_STORE,
    FILE_HOLDER_IS_CODEX,
    FILE_NOT_FOUND,
    FILE_NOT_STORED,
    NOTE_DELETED,
    CodexRuleError,
)
from src.modules.codex.file_holders import register_file_holders
from src.modules.core_storage.dto import Owner
from src.modules.core_storage.models import CoreStorageFile
from src.modules.core_storage.services.files import file_delete, file_get
from src.modules.core_storage.services.ownership import file_owners
from src.modules.core_storage.services.registration import file_register_bytes
from src.modules.core_storage_upload.services import holders as upload_holders
from src.modules.core_storage_upload.services.intake import upload_stream
from tests.modules.codex.file_support import codex_file_attach_bytes

pytestmark = pytest.mark.db

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64


@pytest.fixture
async def codex(db, storage):
    return await codex_crud.codex_create(segment="python", title="Python")


@pytest.fixture
async def note(codex):
    return await note_crud.note_create(parent_code=codex.code, segment="test", title="Тесты")


async def _stored_count() -> int:
    async with session_scope() as s:
        return (await s.execute(select(func.count()).select_from(CoreStorageFile))).scalar_one()


async def _owners(code: str) -> list[Owner]:
    return [place.owner for place in await file_owners(code)]


async def _released(code: str) -> bool:
    return await _owners(code) == [] and (await file_get(code, include_deleted=True)).deleted_at is not None


def _owner(note) -> Owner:
    return Owner(type="CODEX", id=note.code)


async def test_attach_stores_the_file_for_the_note_at_the_end(note):
    first = await codex_file_attach_bytes(note.code, PNG, filename="flow.PNG")
    second = await codex_file_attach_bytes(
        note.code, b"# x", filename="x.md", title="Пример", description="Как писать"
    )

    assert (first.sort, second.sort) == (SORT_DEFAULT, SORT_DEFAULT - SORT_STEP)
    assert await _owners(first.file_code) == [_owner(note)]
    assert (await file_get(first.file_code)).store == "public"
    views = await codex_files.codex_file_views(note.code)
    assert [(v.binding.title, v.original_filename, v.original_extension) for v in views] == [
        ("", "flow", ".PNG"),
        ("Пример", "x", ".md"),
    ]


async def test_a_codex_code_is_refused_by_name_and_nothing_is_stored(codex, note):
    with pytest.raises(CodexRuleError) as refused:
        await codex_file_attach_bytes(codex.code, PNG, filename="x.png")

    assert refused.value.code == FILE_HOLDER_IS_CODEX
    assert await _stored_count() == 0


async def test_a_deleted_note_takes_no_file(note):
    await note_crud.note_delete(note.code)

    with pytest.raises(CodexRuleError) as refused:
        await codex_file_attach_bytes(note.code, PNG, filename="x.png")

    assert refused.value.code == NOTE_DELETED
    assert await _stored_count() == 0


async def test_the_same_content_twice_is_refused_and_keeps_the_owner(note):
    bound = await codex_file_attach_bytes(note.code, PNG, filename="a.png")

    with pytest.raises(CodexRuleError) as refused:
        await codex_file_attach_bytes(note.code, PNG, filename="b.png")

    assert refused.value.code == FILE_ALREADY_ATTACHED
    assert [row.file_code for row in await file_crud.codex_file_list(note.code)] == [bound.file_code]
    assert await _owners(bound.file_code) == [_owner(note)]
    names = {p.owner: (p.original_filename, p.original_extension) for p in await file_owners(bound.file_code)}
    assert names == {_owner(note): ("a", ".png")}


async def test_the_same_content_after_the_file_manager_deleted_it_brings_the_binding_back(note):
    bound = await codex_file_attach_bytes(note.code, PNG, filename="a.png", title="Схема")
    await file_delete(bound.file_code)
    assert await codex_files.codex_file_views(note.code) == []

    back = await codex_file_attach_bytes(note.code, PNG, filename="b.png", title="Новая")

    assert (back.file_code, back.title) == (bound.file_code, "Схема")
    assert [v.binding.file_code for v in await codex_files.codex_file_views(note.code)] == [
        bound.file_code
    ]
    assert await _owners(bound.file_code) == [_owner(note)]


async def test_one_file_in_two_notes_has_two_owners(codex, note):
    other = await note_crud.note_create(parent_code=codex.code, segment="style", title="Стиль")
    bound = await codex_file_attach_bytes(note.code, PNG, filename="a.png")

    again = await codex_files.codex_file_attach_existing(other.code, bound.file_code)

    assert again.file_code == bound.file_code
    assert {o.id for o in await _owners(bound.file_code)} == {note.code, other.code}
    with pytest.raises(CodexRuleError) as refused:
        await codex_files.codex_file_attach_existing(other.code, bound.file_code)
    assert refused.value.code == FILE_ALREADY_ATTACHED
    with pytest.raises(CodexRuleError) as missing:
        await codex_files.codex_file_attach_existing(other.code, "ABCDEF0123")
    assert missing.value.code == FILE_NOT_STORED


async def test_a_binding_refused_after_the_storage_gives_the_owner_back(note, monkeypatch):
    async def refuse(**_):
        raise CodexRuleError(NOTE_DELETED, "deleted meanwhile")

    monkeypatch.setattr(file_crud, "codex_file_create", refuse)

    with pytest.raises(CodexRuleError):
        await codex_file_attach_bytes(note.code, PNG, filename="x.png")

    async with session_scope() as s:
        stored = (await s.execute(select(CoreStorageFile))).scalars().all()
    assert len(stored) == 1 and await _released(stored[0].code)


async def test_edit_reorder_and_detach(note):
    codes = [
        (await codex_file_attach_bytes(note.code, bytes([n]), filename=f"{n}.txt")).file_code
        for n in range(3)
    ]

    row = await file_crud.codex_file_update(note.code, codes[0], description="Что внутри")
    await file_crud.codex_file_reorder(note.code, [codes[2]])
    with pytest.raises(CodexRuleError) as refused:
        await file_crud.codex_file_reorder(note.code, ["0000000000"])

    assert (row.title, row.description) == ("", "Что внутри")
    assert refused.value.code == FILE_NOT_FOUND
    assert [r.file_code for r in await file_crud.codex_file_list(note.code)] == [codes[2], codes[0], codes[1]]

    assert await codex_files.codex_file_detach(note.code, codes[1]) is True
    assert await codex_files.codex_file_detach(note.code, codes[1]) is False
    assert await _released(codes[1])
    assert {r.note_code for r in await file_crud.codex_file_list_by_file(codes[0])} == {note.code}


# ── deletions ─────────────────────────────────────────────────────────────────


async def test_a_soft_deleted_note_keeps_its_files_and_comes_back_with_them(note):
    bound = await codex_file_attach_bytes(note.code, PNG, filename="a.png")

    await note_crud.note_delete(note.code)

    assert await _owners(bound.file_code) == [_owner(note)]
    await note_crud.note_restore(note.code)
    assert [row.file_code for row in await file_crud.codex_file_list(note.code)] == [bound.file_code]


async def test_a_soft_deleted_codex_keeps_its_notes_files(codex, note):
    bound = await codex_file_attach_bytes(note.code, PNG, filename="a.png")

    await codex_crud.codex_delete(codex.code)

    assert await _owners(bound.file_code) == [_owner(note)]


async def test_a_note_of_a_soft_deleted_codex_takes_and_gives_up_no_file(codex, note):
    bound = await codex_file_attach_bytes(note.code, PNG, filename="a.png")
    await codex_crud.codex_delete(codex.code)

    with pytest.raises(CodexRuleError) as attach_refused:
        await codex_file_attach_bytes(note.code, b"new", filename="b.txt")
    with pytest.raises(CodexRuleError) as detach_refused:
        await codex_files.codex_file_detach(note.code, bound.file_code)

    assert attach_refused.value.code == detach_refused.value.code == CODEX_DELETED
    assert await _stored_count() == 1
    assert [row.file_code for row in await file_crud.codex_file_list(note.code)] == [bound.file_code]
    assert await _owners(bound.file_code) == [_owner(note)]


async def test_a_file_of_another_store_is_refused_and_nothing_is_written(note):
    private = await file_register_bytes(b"secret", store="private", owner=Owner("other", "1"))

    with pytest.raises(CodexRuleError) as refused:
        await codex_files.codex_file_attach_existing(note.code, private.code)

    assert refused.value.code == FILE_FOREIGN_STORE
    assert await file_crud.codex_file_list(note.code) == []
    assert await _owners(private.code) == [Owner("other", "1")]


async def test_an_attach_racing_a_detach_of_the_same_file_leaves_pairs(note, monkeypatch):
    """The attach is stopped after the storage took the file and before its row; the detach
    started then must wait for it, or it releases the owner the attach's row would stand on."""
    bound = await codex_file_attach_bytes(note.code, PNG, filename="a.png")
    reached, go = asyncio.Event(), asyncio.Event()
    real_create = file_crud.codex_file_create

    async def paused(**kwargs):
        reached.set()
        await go.wait()
        return await real_create(**kwargs)

    monkeypatch.setattr(file_crud, "codex_file_create", paused)
    attaching = asyncio.create_task(
        codex_file_attach_bytes(note.code, PNG, filename="b.png")
    )
    await reached.wait()
    detaching = asyncio.create_task(codex_files.codex_file_detach(note.code, bound.file_code))
    await asyncio.wait([detaching], timeout=0.5)
    go.set()
    attached, detached = await asyncio.gather(attaching, detaching, return_exceptions=True)

    bound_now = bool(await file_crud.codex_file_list(note.code))
    held_now = bool(await _owners(bound.file_code))
    assert bound_now == held_now
    assert isinstance(attached, CodexRuleError) and detached is True and not bound_now


async def test_an_upload_still_streaming_does_not_hold_the_note(note, storage, monkeypatch):
    """A lock held over the stream would keep the detach waiting until the upload ends — here
    never, the gate is still shut. The upload goes the application's way: through the holder this
    module registers in ``core_storage_upload``."""
    monkeypatch.setattr(upload_holders, "_holders", {})
    register_file_holders()
    other = await codex_file_attach_bytes(note.code, b"other", filename="o.txt")
    started, gate = asyncio.Event(), asyncio.Event()

    async def slow_body():
        yield b"first part "
        started.set()
        await gate.wait()
        yield b"the rest"

    uploading = asyncio.create_task(
        upload_stream(f"CODEX@{note.code}", slow_body(), payload={}, filename="slow.txt")
    )
    await started.wait()

    detached = await asyncio.wait_for(codex_files.codex_file_detach(note.code, other.file_code), 2.0)
    gate.set()
    uploaded = (await uploading)["code"].removeprefix("FILE@")

    assert detached is True
    assert [row.file_code for row in await file_crud.codex_file_list(note.code)] == [uploaded]
    assert await _owners(uploaded) == [_owner(note)]
    assert [path for path in storage.tmp.rglob("*") if path.is_file()] == []


@pytest.mark.parametrize(
    ("field", "value"),
    [("title", "Схема\x00"), ("title", "две\nстроки"), ("description", "звонок\x07")],
)
async def test_a_control_character_is_refused_by_the_service_before_the_storage(
    note, field, value
):
    from src.modules.codex.errors import FILE_CONTROL_CHARACTER

    with pytest.raises(CodexRuleError) as refused:
        await codex_file_attach_bytes(note.code, PNG, filename="x.png", **{field: value})

    assert refused.value.code == FILE_CONTROL_CHARACTER
    assert refused.value.params == {"field": field}
    assert await _stored_count() == 0
    assert await file_crud.codex_file_list(note.code) == []


async def test_a_retitle_with_a_control_character_changes_nothing(note):
    from src.modules.codex.errors import FILE_CONTROL_CHARACTER

    bound = await codex_file_attach_bytes(note.code, PNG, filename="x.png", title="Было")

    with pytest.raises(CodexRuleError) as refused:
        await codex_files.codex_file_retitle(note.code, bound.file_code, title="Ста\x00ло")

    assert refused.value.code == FILE_CONTROL_CHARACTER
    assert (await file_crud.codex_file_get(note.code, bound.file_code)).title == "Было"


async def test_an_upload_is_hashed_once(note, storage, monkeypatch):
    import hashlib
    from types import SimpleNamespace

    from src.modules.core_storage.services import registration

    made: list[object] = []

    def counted(*args):
        digest = hashlib.sha256(*args)
        made.append(digest)
        return digest

    monkeypatch.setattr(registration, "hashlib", SimpleNamespace(sha256=counted))

    bound = await codex_file_attach_bytes(note.code, b"part one, part two", filename="two.txt")

    assert len(made) == 1
    assert (await file_get(bound.file_code)).sha256 == hashlib.sha256(b"part one, part two").hexdigest()


async def test_the_files_list_costs_the_same_statements_for_any_number_of_files(codex, note):
    from sqlalchemy import event

    from src.core.database import get_engine

    other = await note_crud.note_create(parent_code=codex.code, segment="many", title="Много")
    for n in range(2):
        await codex_file_attach_bytes(note.code, PNG + bytes([n]), filename=f"{n}.png")
    for n in range(12):
        await codex_file_attach_bytes(other.code, PNG + bytes([100 + n]), filename=f"{n}.png")

    async def statements(note_code: str) -> tuple[int, int]:
        seen: list[str] = []

        def count(conn, cursor, statement, *args):
            seen.append(statement)

        sync_engine = get_engine().sync_engine
        event.listen(sync_engine, "before_cursor_execute", count)
        try:
            views = await codex_files.codex_file_views(note_code)
        finally:
            event.remove(sync_engine, "before_cursor_execute", count)
        return len(seen), len(views)

    few_statements, few_views = await statements(note.code)
    many_statements, many_views = await statements(other.code)

    assert (few_views, many_views) == (2, 12)
    assert few_statements == many_statements
    names = [view.original_filename for view in await codex_files.codex_file_views(other.code)]
    assert names == [str(n) for n in range(12)]


async def test_a_hard_deleted_branch_releases_the_files_of_every_note_in_it(codex, note):
    child = await note_crud.note_create(parent_code=note.code, segment="fixtures", title="Фикстуры")
    sibling = await note_crud.note_create(parent_code=codex.code, segment="style", title="Стиль")
    on_note = await codex_file_attach_bytes(note.code, b"1", filename="1.txt")
    on_child = await codex_file_attach_bytes(child.code, b"2", filename="2.txt")
    kept = await codex_file_attach_bytes(sibling.code, b"3", filename="3.txt")

    assert await note_crud.note_delete(note.code, with_branch=True, hard=True) is True

    assert await _released(on_note.file_code)
    assert await _released(on_child.file_code)
    assert await _owners(kept.file_code) == [_owner(sibling)]


async def test_a_hard_deleted_codex_releases_its_notes_files(codex, note):
    bound = await codex_file_attach_bytes(note.code, PNG, filename="a.png")

    assert await codex_crud.codex_delete(codex.code, hard=True) is True

    assert await _released(bound.file_code)
    assert await file_crud.codex_file_list(note.code) == []
