"""The person's upload into a task: ``POST /storage/upload?holder=TASK@…`` with the file as the body.

The route is ``core_storage_upload``'s; the holders ``TASK@``, ``NOTE@`` and ``STAGE@`` are this
module's (``file_holders.py``), registered as ``TasksModule.configure`` does. The body streams
into the storage under the name in ``filename``; the title and description ride in the query, the
place is the holder's code. Every refusal is checked by the state after it — no stored file, no
binding, no spare bytes in the storage's temporary folder — because the upload writes in two
transactions and an answer alone would not show a half-written one.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from sqlalchemy import func, select

from src.core.database import session_scope
from src.core.router.storage import STORAGE_PREFIX
from src.modules.core_storage import settings as storage_settings
from src.modules.core_storage.models import CoreStorageFile
from src.modules.core_storage.services.ownership import file_owners
from src.modules.core_storage_upload.api import router as upload_router
from src.modules.core_storage_upload.constants import ROUTER_PREFIX as UPLOAD_PREFIX
from src.modules.core_storage_upload.services import holders as upload_holders
from src.modules.tasks import files as task_files
from src.modules.tasks.constants import FILE_TITLE_MAX, TYPE_EXTENDED
from src.modules.tasks.crud import file as file_crud
from src.modules.tasks.crud import note as note_crud
from src.modules.tasks.crud import stage as stage_crud
from src.modules.tasks.crud import task as task_crud
from src.modules.tasks.file_holders import register_file_holders
from src.modules.workspace.crud import workspace as workspace_crud
from tests.modules.tasks.file_support import task_file_attach_bytes

pytestmark = pytest.mark.db

TASKS = "/internal/workbench/tasks"
UPLOAD = f"{STORAGE_PREFIX}{UPLOAD_PREFIX}/upload"
# The app's own page, as the test client's host names it: the upload takes a browser's request
# only from there.
OWN_PAGE = {"Origin": "http://test"}
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
MB = 1024 * 1024


@pytest.fixture(autouse=True)
def upload_route(app, monkeypatch: pytest.MonkeyPatch) -> None:
    """The upload module's route next to the module's own, and the holders the module registers
    in fresh registries — as the assembled app has them."""
    app.include_router(upload_router, prefix=f"{STORAGE_PREFIX}{UPLOAD_PREFIX}")
    monkeypatch.setattr(upload_holders, "_holders", {})
    register_file_holders()


@pytest.fixture
async def workspace(client, storage):
    return await workspace_crud.workspace_create(title="Работа")


@pytest.fixture
async def task(workspace):
    return await task_crud.task_create(
        workspace_code=workspace.code, title="Выпуск", type=TYPE_EXTENDED
    )


@pytest.fixture
def one_mb_ceiling(monkeypatch: pytest.MonkeyPatch) -> int:
    monkeypatch.setattr(storage_settings, "_current", SimpleNamespace(max_file_size_mb=1))
    return MB


async def _stored_count() -> int:
    async with session_scope() as s:
        return (await s.execute(select(func.count()).select_from(CoreStorageFile))).scalar_one()


def _spare_files(storage) -> list[str]:
    return [path.name for path in storage.tmp.rglob("*") if path.is_file()]


class _UnreadBody:
    """A request body that must not be read: a refusal due before the body pulls nothing."""

    def __init__(self) -> None:
        self.pulled = False

    def __aiter__(self):
        return self

    async def __anext__(self) -> bytes:
        self.pulled = True
        raise AssertionError("the body was read before the refusal")


async def _upload(client, holder: str, data: bytes, **query):
    return await client.post(
        UPLOAD, params={"holder": holder, **query}, content=data, headers=OWN_PAGE
    )


async def test_the_body_becomes_a_file_of_the_task_under_its_own_name(client, task, storage):
    response = await _upload(
        client, f"TASK@{task.code}", PNG,
        filename="Снимок экрана.PNG", title="Вход", description="Экран после входа",
    )

    assert response.status_code == 201, response.text
    row = response.json()
    assert {key: row[key] for key in (
        "task_code", "note_code", "stage_code", "title", "description",
        "original_filename", "original_extension", "mime", "type", "size",
    )} == {
        "task_code": f"TASK@{task.code}",
        "note_code": None,
        "stage_code": None,
        "title": "Вход",
        "description": "Экран после входа",
        "original_filename": "Снимок экрана",
        "original_extension": ".PNG",
        "mime": "image/png",
        "type": "image",
        "size": len(PNG),
    }
    rows = await file_crud.task_file_list(task.code)
    assert [f"FILE@{one.file_code}" for one in rows] == [row["code"]]
    assert _spare_files(storage) == []


async def test_a_name_that_came_with_a_path_keeps_its_last_segment(client, task):
    response = await _upload(
        client, f"TASK@{task.code}", b"log line\n", filename="C:\\логи\\сборка.log"
    )

    assert response.status_code == 201, response.text
    assert (response.json()["original_filename"], response.json()["original_extension"]) == ("сборка", ".log")


async def test_a_holder_code_is_read_in_any_case(client, task):
    response = await _upload(client, f"task@{task.code.lower()}", b"x", filename="x.txt")

    assert response.status_code == 201, response.text
    assert response.json()["task_code"] == f"TASK@{task.code}"


async def test_a_new_file_goes_below_the_others(client, task):
    first = await task_file_attach_bytes(task.code, b"first", filename="a.txt")

    response = await _upload(client, f"TASK@{task.code}", b"second", filename="b.txt")

    assert response.status_code == 201, response.text
    assert [row.file_code for row in await file_crud.task_file_list(task.code)] == [
        first.file_code, response.json()["code"].removeprefix("FILE@"),
    ]


async def test_a_file_lands_on_the_note_or_the_stage_it_names(client, task):
    note = await note_crud.task_note_add(task_code=task.code, title="Схема")
    stage = await stage_crud.stage_create(task_code=task.code, title="Сборка")

    on_note = await _upload(client, f"NOTE@{note.code}", b"n", filename="n.txt")
    on_stage = await _upload(client, f"STAGE@{stage.code}", b"s", filename="s.txt")

    assert on_note.status_code == on_stage.status_code == 201
    assert (on_note.json()["task_code"], on_note.json()["note_code"]) == (
        f"TASK@{task.code}", f"NOTE@{note.code}"
    )
    assert (on_stage.json()["task_code"], on_stage.json()["stage_code"]) == (
        f"TASK@{task.code}", f"STAGE@{stage.code}"
    )


async def test_the_same_bytes_again_are_refused_with_the_file_they_are(client, task):
    first = await _upload(client, f"TASK@{task.code}", PNG, filename="экран.png", title="Вход")

    again = await _upload(
        client, f"TASK@{task.code}", PNG, filename="другое имя.png", title="Другое"
    )

    assert again.status_code == 409
    body = again.json()
    assert body["code"] == "tasks.file.already_attached"
    assert body["params"] == {"file": first.json()["code"], "name": "Вход", "type": "image"}
    rows = await file_crud.task_file_list(task.code)
    assert [(row.title, row.note_code) for row in rows] == [("Вход", None)]
    view = await task_files.task_file_view(task.code, rows[0].file_code)
    assert view.original_filename == "экран"
    assert await _stored_count() == 1


async def test_a_body_announced_over_the_ceiling_is_413_before_a_byte_is_read(
    client, task, storage, one_mb_ceiling
):
    body = _UnreadBody()

    response = await client.post(
        UPLOAD,
        params={"holder": f"TASK@{task.code}", "filename": "big.bin"},
        content=body,
        headers={**OWN_PAGE, "Content-Length": str(one_mb_ceiling + 1)},
    )

    assert body.pulled is False
    assert response.status_code == 413
    assert response.json()["code"] == "core_storage_upload.file.too_large"
    assert response.json()["params"] == {"limit": one_mb_ceiling, "limit_mb": 1}
    assert await file_crud.task_file_list(task.code) == []
    assert await _stored_count() == 0
    assert _spare_files(storage) == []


async def test_a_stream_running_past_the_ceiling_is_413_and_nothing_is_stored(
    client, task, storage, one_mb_ceiling
):
    async def chunks():
        for _ in range(3):
            yield b"x" * (one_mb_ceiling // 2 + 1)

    response = await client.post(
        UPLOAD,
        params={"holder": f"TASK@{task.code}", "filename": "big.bin"},
        content=chunks(),
        headers=OWN_PAGE,
    )

    assert response.status_code == 413
    assert response.json()["code"] == "core_storage_upload.file.too_large"
    assert await file_crud.task_file_list(task.code) == []
    assert await _stored_count() == 0
    assert _spare_files(storage) == []


async def test_a_deleted_note_is_no_place_and_nothing_is_stored(client, task):
    from src.modules.notes.crud import note as notes_crud

    note = await note_crud.task_note_add(task_code=task.code, title="Удалённая")
    await notes_crud.note_delete(note.code)

    response = await _upload(client, f"NOTE@{note.code}", PNG, filename="x.png")

    assert response.status_code == 400
    assert response.json()["code"] == "tasks.file.foreign_place"
    assert await file_crud.task_file_list(task.code) == []
    assert await _stored_count() == 0


@pytest.mark.parametrize(
    ("holder", "code"),
    [
        ("TASK@0000000000", "tasks.task.not_found"),
        ("NOTE@0000000000", "tasks.note.not_found"),
        ("STAGE@0000000000", "tasks.stage.not_found"),
    ],
)
async def test_an_unknown_holder_of_this_module_is_404_and_nothing_is_stored(
    client, task, storage, holder, code
):
    body = _UnreadBody()

    response = await client.post(
        UPLOAD,
        params={"holder": holder, "filename": "x.png"},
        content=body,
        headers={**OWN_PAGE, "Content-Length": "16"},
    )

    assert body.pulled is False
    assert response.status_code == 404
    assert response.json()["code"] == code
    assert await _stored_count() == 0
    assert _spare_files(storage) == []


async def test_a_deleted_task_takes_no_file(client, task):
    note = await note_crud.task_note_add(task_code=task.code, title="Схема")
    await task_crud.task_delete(task.code)

    on_task = await _upload(client, f"TASK@{task.code}", PNG, filename="x.png")
    on_note = await _upload(client, f"NOTE@{note.code}", PNG, filename="x.png")

    assert (on_task.status_code, on_task.json()["code"]) == (409, "tasks.task.deleted")
    assert (on_note.status_code, on_note.json()["code"]) == (409, "tasks.task.deleted")
    assert await file_crud.task_file_list(task.code) == []
    assert await _stored_count() == 0


async def test_a_title_over_its_limit_is_400_before_the_body(client, task, storage):
    """The limit is the holder's: the upload module does not know it, so the holder's check
    refuses it — before a byte of the body is read."""
    body = _UnreadBody()

    response = await client.post(
        UPLOAD,
        params={
            "holder": f"TASK@{task.code}",
            "filename": "x.png",
            "title": "т" * (FILE_TITLE_MAX + 1),
        },
        content=body,
        headers={**OWN_PAGE, "Content-Length": "16"},
    )

    assert body.pulled is False
    assert response.status_code == 400
    assert await _stored_count() == 0
    assert _spare_files(storage) == []


@pytest.mark.parametrize(
    ("field", "value", "code", "params"),
    [
        ("filename", "снимок\x00.png", "core_storage_upload.filename.control_character", None),
        ("filename", "снимок\n.png", "core_storage_upload.filename.control_character", None),
        ("title", "Вход\x00", "tasks.file.control_character", {"field": "title"}),
        ("title", "Вход\tэкран", "tasks.file.control_character", {"field": "title"}),
        ("description", "после\x00входа", "tasks.file.control_character", {"field": "description"}),
        ("description", "после\x07входа", "tasks.file.control_character", {"field": "description"}),
    ],
)
async def test_a_control_character_is_400_before_the_body(
    client, task, storage, field, value, code, params
):
    """The name is the upload module's to refuse — one rule for every holder; the title and the
    description are the holder's."""
    body = _UnreadBody()
    query = {"holder": f"TASK@{task.code}", "filename": "x.png", field: value}

    response = await client.post(
        UPLOAD,
        params=query,
        content=body,
        headers={**OWN_PAGE, "Content-Length": "16"},
    )

    assert body.pulled is False
    assert response.status_code == 400
    assert response.json()["code"] == code
    assert response.json()["params"] == params
    assert await file_crud.task_file_list(task.code) == []
    assert await _stored_count() == 0
    assert _spare_files(storage) == []


async def test_a_description_keeps_its_line_breaks(client, task):
    response = await _upload(
        client,
        f"TASK@{task.code}",
        PNG,
        filename="x.png",
        description="первая строка\nвторая\tс табом",
    )

    assert response.status_code == 201, response.text
    assert response.json()["description"] == "первая строка\nвторая\tс табом"


async def test_a_retitle_with_a_nul_is_400_and_changes_nothing(client, task):
    bound = await task_file_attach_bytes(task.code, PNG, filename="x.png", title="Было")

    response = await client.patch(
        f"{TASKS}/{task.code}/files/{bound.file_code}", json={"title": "Ста\x00ло"}
    )

    assert response.status_code == 400
    assert response.json()["code"] == "tasks.file.control_character"
    assert (await file_crud.task_file_get(task.code, bound.file_code)).title == "Было"


async def test_a_page_of_another_site_is_refused_before_the_body(client, task):
    response = await client.post(
        UPLOAD,
        params={"holder": f"TASK@{task.code}", "filename": "x.png"},
        content=PNG,
        headers={"Origin": "http://evil.example", "Content-Type": "text/plain"},
    )

    assert response.status_code == 403
    assert response.json()["code"] == "origin_refused"
    assert await file_crud.task_file_list(task.code) == []
    assert await _stored_count() == 0


async def test_the_app_s_own_page_is_let_through(client, task):
    response = await client.post(
        UPLOAD,
        params={"holder": f"TASK@{task.code}", "filename": "x.png"},
        content=PNG,
        headers={"Origin": "http://test"},
    )

    assert response.status_code == 201, response.text
    owners = await file_owners(response.json()["code"].removeprefix("FILE@"))
    assert [place.owner.id for place in owners] == [task.code]
