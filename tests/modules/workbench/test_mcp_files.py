"""workbench MCP: attaching a file, listing a holder's files, reading what a file is.

``attach_file`` takes the holder by its code's prefix — a task, a task note, a stage, a codex note
— and the file by a path on the server or by the code of a file stored already. The answer gives
the code to put into a text: ``IMAGE@`` for a picture, ``FILE@`` for anything else. Every refusal
is checked by what it leaves behind: no binding, no storage owner, the source file in place.

``task_get`` and ``codex_get`` list a holder's files by code, title and description only;
``file_get``, the ``workbench://file/{code}`` resource and ``interface_open`` read one.
"""

from __future__ import annotations

import base64
from datetime import timedelta
from pathlib import Path

import pytest
from fastmcp.exceptions import ToolError
from mcp.shared.exceptions import McpError
from sqlalchemy import update

from src.core.database import write_scope
from src.core.utils.date import utc_now
from src.modules.codex import files as codex_files
from src.modules.codex.crud import codex as codex_crud
from src.modules.codex.crud import file as codex_file_crud
from src.modules.codex.crud import mount as mount_crud
from src.modules.codex.crud import note as codex_note_crud
from src.modules.core_storage.dto import Owner
from src.modules.core_storage.models import CoreStorageFileOwner
from src.modules.core_storage.services.files import file_delete, file_get_many
from src.modules.core_storage.services.ownership import file_owners
from src.modules.core_storage.services.registration import file_register_bytes
from src.modules.tasks import files as task_files
from src.modules.tasks.constants import TYPE_EXTENDED
from src.modules.tasks.crud import file as task_file_crud
from src.modules.tasks.crud import note as task_note_crud
from src.modules.tasks.crud import stage as stage_crud
from src.modules.tasks.crud import task as task_crud
from src.modules.workspace.crud.workspace import workspace_create
from tests.modules.tasks.file_support import task_file_attach_bytes

pytestmark = pytest.mark.db

PNG = bytes.fromhex("89504e470d0a1a0a0000000d49484452") + b"\x00" * 64
ZIP = b"PK\x03\x04" + b"\x00" * 64


@pytest.fixture
async def here(call, workspace, storage):
    await call("workspace_use", workspace_code=workspace.code)
    return workspace


@pytest.fixture
async def task(here):
    return await task_crud.task_create(workspace_code=here.code, title="Выпуск", type=TYPE_EXTENDED)


@pytest.fixture
def source(tmp_path: Path) -> Path:
    path = tmp_path / "work" / "schema.md"
    path.parent.mkdir()
    path.write_text("# Схема\n", encoding="utf-8")
    return path


@pytest.fixture
def shot(tmp_path: Path) -> Path:
    path = tmp_path / "Shot.PNG"
    path.write_bytes(PNG)
    return path


@pytest.fixture
def no_browser(monkeypatch):
    opened: list[str] = []

    def open_url(url: str) -> bool:
        opened.append(url)
        return True

    monkeypatch.setattr("src.modules.workbench.tools.interface.webbrowser.open", open_url)
    return opened


async def _codex_note(workspace_code: str, *, writable: bool = True):
    codex = await codex_crud.codex_create(segment="python", title="Python")
    await mount_crud.mount_add(codex.code, workspace_code, agent_can_edit=writable)
    return await codex_note_crud.note_create(parent_code=codex.code, segment="test", title="Тесты")


async def _stored_count(storage) -> int:
    return sum(1 for path in (storage.root / "public").rglob("*") if path.is_file())


async def _owners(code: str) -> set[Owner]:
    return {place.owner for place in await file_owners(code)}


async def _brought_earlier(code: str, owner: Owner) -> None:
    """Make ``owner`` the file's earliest place — the order a storage-wide name choice goes by;
    rows written in one second would otherwise tie and fall to their random codes."""
    async with write_scope() as s:
        await s.execute(
            update(CoreStorageFileOwner)
            .where(
                CoreStorageFileOwner.file_code == code,
                CoreStorageFileOwner.owner_type == owner.type,
                CoreStorageFileOwner.owner_id == owner.id,
            )
            .values(created_at=utc_now() - timedelta(hours=1))
        )


async def _names(code: str) -> dict[Owner, str]:
    return {
        place.owner: place.original_filename + place.original_extension
        for place in await file_owners(code)
    }


# ── attach by path ────────────────────────────────────────────────────────────


async def test_a_path_on_the_server_is_attached_to_the_task_and_left_in_place(call, task, source):
    answer = await call(
        "attach_file", code=f"TASK@{task.code}", path=str(source), title="Схема", description="ER"
    )

    code = answer["code"].removeprefix("FILE@")
    assert answer == {
        "workspace": answer["workspace"],
        "workspace_title": "Работа",
        "code": f"FILE@{code}",
        "insert": f"FILE@{code}",
        "title": "Схема",
        "description": "ER",
    }
    [row] = await task_file_crud.task_file_list(task.code)
    assert (row.file_code, row.note_code, row.stage_code) == (code, None, None)
    assert await _owners(code) == {Owner("TASK", task.code)}
    assert source.read_text(encoding="utf-8") == "# Схема\n"


async def test_a_picture_is_inserted_as_an_image(call, task, shot):
    answer = await call("attach_file", code=f"TASK@{task.code}", path=str(shot))

    assert answer["insert"] == answer["code"].replace("FILE@", "IMAGE@")
    assert (answer["title"], answer["description"]) == ("", "")


async def test_a_task_note_holds_it_in_its_task(call, task, source):
    note = await task_note_crud.task_note_add(task_code=task.code, title="Схема")

    answer = await call("attach_file", code=f"NOTE@{note.code}", path=str(source))

    row = await task_file_crud.task_file_get(task.code, answer["code"].removeprefix("FILE@"))
    assert (row.note_code, row.stage_code) == (note.code, None)


async def test_a_stage_holds_it_in_its_task(call, task, shot):
    stage = await stage_crud.stage_create(task_code=task.code, title="Сборка")

    answer = await call("attach_file", code=f"STAGE@{stage.code}", path=str(shot))

    row = await task_file_crud.task_file_get(task.code, answer["code"].removeprefix("FILE@"))
    assert (row.note_code, row.stage_code) == (None, stage.code)


async def test_a_writable_codex_note_holds_it(call, here, source):
    note = await _codex_note(here.code)

    answer = await call("attach_file", code=f"CODEX@{note.code}", path=str(source))

    code = answer["code"].removeprefix("FILE@")
    assert [row.file_code for row in await codex_file_crud.codex_file_list(note.code)] == [code]
    assert await _owners(code) == {Owner("CODEX", note.code)}


async def test_the_same_content_twice_in_one_task_is_refused(call, task, source):
    first = await call("attach_file", code=f"TASK@{task.code}", path=str(source))

    with pytest.raises(ToolError, match=f"{first['code']} is in TASK@{task.code} already"):
        await call("attach_file", code=f"TASK@{task.code}", path=str(source))

    assert len(await task_file_crud.task_file_list(task.code)) == 1


# ── attach a stored file ──────────────────────────────────────────────────────


async def test_a_stored_file_is_attached_to_one_more_holder_under_the_same_code(call, task, here):
    bound = await task_file_attach_bytes(task.code, PNG, filename="shot.png")
    note = await _codex_note(here.code)

    answer = await call(
        "attach_file", code=f"CODEX@{note.code}", file=f"FILE@{bound.file_code}", title="Экран"
    )

    assert answer["code"] == f"FILE@{bound.file_code}"
    assert answer["insert"] == f"IMAGE@{bound.file_code}"
    assert await _owners(bound.file_code) == {Owner("TASK", task.code), Owner("CODEX", note.code)}


async def test_an_image_code_names_the_stored_file_too(call, task, here):
    bound = await task_file_attach_bytes(task.code, PNG, filename="shot.png")
    other = await task_crud.task_create(workspace_code=here.code, title="Отчёт")

    answer = await call("attach_file", code=f"TASK@{other.code}", file=f"IMAGE@{bound.file_code}")

    assert answer["code"] == f"FILE@{bound.file_code}"


async def test_a_stored_file_of_another_workspace_is_refused(call, task):
    elsewhere = await workspace_create(title="Личное")
    foreign = await task_crud.task_create(workspace_code=elsewhere.code, title="Чужая")
    bound = await task_file_attach_bytes(foreign.code, PNG, filename="shot.png")

    with pytest.raises(ToolError, match="is not attached to anything in 'Работа'"):
        await call("attach_file", code=f"TASK@{task.code}", file=f"FILE@{bound.file_code}")

    assert await task_file_crud.task_file_list(task.code) == []
    assert await _owners(bound.file_code) == {Owner("TASK", foreign.code)}


async def test_an_unknown_stored_file_is_refused(call, task):
    with pytest.raises(ToolError, match="FILE@0000000000 does not exist"):
        await call("attach_file", code=f"TASK@{task.code}", file="FILE@0000000000")

    assert await task_file_crud.task_file_list(task.code) == []


async def test_a_stored_file_no_holder_binds_is_refused(call, task):
    """An owner left behind by a failed release, before the reconciliation finds it: the file is
    live and bound nowhere, so no workspace sees it — and none may take it."""
    elsewhere = await workspace_create(title="Личное")
    foreign = await task_crud.task_create(workspace_code=elsewhere.code, title="Чужая")
    left = await file_register_bytes(PNG, store="public", owner=Owner("TASK", foreign.code))

    with pytest.raises(ToolError, match=f"FILE@{left.code} does not exist"):
        await call("attach_file", code=f"TASK@{task.code}", file=f"FILE@{left.code}")

    assert await task_file_crud.task_file_list(task.code) == []
    assert await _owners(left.code) == {Owner("TASK", foreign.code)}


async def test_a_stored_file_takes_the_name_it_has_here_not_another_workspace_s(call, task, here):
    elsewhere = await workspace_create(title="Личное")
    foreign = await task_crud.task_create(workspace_code=elsewhere.code, title="Чужая")
    bound = await task_file_attach_bytes(
        foreign.code, PNG, filename="acme-contract-2026.png"
    )
    await _brought_earlier(bound.file_code, Owner("TASK", foreign.code))
    await task_files.task_file_attach_existing(task.code, bound.file_code, filename="notes.png")
    other = await task_crud.task_create(workspace_code=here.code, title="Отчёт")

    await call("attach_file", code=f"TASK@{other.code}", file=f"FILE@{bound.file_code}")

    assert await _names(bound.file_code) == {
        Owner("TASK", foreign.code): "acme-contract-2026.png",
        Owner("TASK", task.code): "notes.png",
        Owner("TASK", other.code): "notes.png",
    }


async def test_a_stored_file_nameless_here_stays_nameless(call, task, here):
    elsewhere = await workspace_create(title="Личное")
    foreign = await task_crud.task_create(workspace_code=elsewhere.code, title="Чужая")
    bound = await task_file_attach_bytes(
        foreign.code, PNG, filename="acme-contract-2026.png"
    )
    await _brought_earlier(bound.file_code, Owner("TASK", foreign.code))
    await task_files.task_file_attach_existing(task.code, bound.file_code, filename="")
    other = await task_crud.task_create(workspace_code=here.code, title="Отчёт")

    await call("attach_file", code=f"TASK@{other.code}", file=f"FILE@{bound.file_code}")

    assert (await _names(bound.file_code))[Owner("TASK", other.code)] == ""


async def test_a_holder_taking_its_file_back_keeps_its_own_name(call, task, here):
    """A released place revived by attaching the file again: its row knows the name it had."""
    bound = await task_file_attach_bytes(task.code, PNG, filename="first.png")
    other = await task_crud.task_create(workspace_code=here.code, title="Отчёт")
    await task_files.task_file_attach_existing(other.code, bound.file_code, filename="second.png")
    await task_files.task_file_detach(task.code, bound.file_code)

    await call("attach_file", code=f"TASK@{task.code}", file=f"FILE@{bound.file_code}")

    assert (await _names(bound.file_code))[Owner("TASK", task.code)] == "first.png"


# ── refusals that write nothing ───────────────────────────────────────────────


async def test_a_read_only_codex_note_is_refused_before_anything_is_stored(
    call, here, source, storage
):
    note = await _codex_note(here.code, writable=False)

    with pytest.raises(ToolError, match="not editable for you"):
        await call("attach_file", code=f"CODEX@{note.code}", path=str(source))

    assert await codex_file_crud.codex_file_list(note.code) == []
    assert await _stored_count(storage) == 0


async def test_a_codex_itself_is_refused(call, here, source, storage):
    note = await _codex_note(here.code)

    with pytest.raises(ToolError, match="is a codex, not a note"):
        await call("attach_file", code=f"CODEX@{note.codex_code}", path=str(source))

    assert await _stored_count(storage) == 0


async def test_a_codex_not_mounted_here_is_refused(call, here, source, storage):
    codex = await codex_crud.codex_create(segment="vue", title="Vue")
    note = await codex_note_crud.note_create(parent_code=codex.code, segment="ui", title="UI")

    with pytest.raises(ToolError, match="not in a codex mounted into 'Работа'"):
        await call("attach_file", code=f"CODEX@{note.code}", path=str(source))

    assert await _stored_count(storage) == 0


async def test_a_task_of_another_workspace_is_refused_by_name(call, here, source, storage):
    elsewhere = await workspace_create(title="Личное")
    foreign = await task_crud.task_create(workspace_code=elsewhere.code, title="Чужая")

    with pytest.raises(ToolError, match="Личное"):
        await call("attach_file", code=f"TASK@{foreign.code}", path=str(source))

    assert await task_file_crud.task_file_list(foreign.code) == []
    assert await _stored_count(storage) == 0


async def test_a_deleted_task_is_refused(call, task, source, storage):
    await task_crud.task_delete(task.code)

    with pytest.raises(ToolError, match="is deleted"):
        await call("attach_file", code=f"TASK@{task.code}", path=str(source))

    assert await _stored_count(storage) == 0


async def test_a_title_over_the_limit_is_refused_before_anything_is_stored(
    call, task, source, storage
):
    with pytest.raises(ToolError, match="File title"):
        await call("attach_file", code=f"TASK@{task.code}", path=str(source), title="я" * 257)

    assert await task_file_crud.task_file_list(task.code) == []
    assert await _stored_count(storage) == 0


async def _stored_rows() -> int:
    from sqlalchemy import func, select

    from src.core.database import session_scope
    from src.modules.core_storage.models import CoreStorageFile

    async with session_scope() as s:
        return (await s.execute(select(func.count()).select_from(CoreStorageFile))).scalar_one()


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("title", "Вход\x00"),
        ("title", "line1\nline2"),
        ("title", "звонок\x07"),
        ("description", "после\x00входа"),
        ("description", "после\x07входа"),
    ],
)
@pytest.mark.parametrize("way", ["path", "upload"])
async def test_a_control_character_in_the_title_or_description_is_refused_before_anything_is_stored(
    call, task, source, storage, field, value, way
):
    """The same rule as the person's upload: a title is one line, a description is prose with
    its line breaks and tabs; neither holds another control character, and U+0000 PostgreSQL
    cannot store at all. Refused before the storage and before an upload address is issued."""
    arguments = {"path": str(source)} if way == "path" else {}

    with pytest.raises(ToolError, match="control character"):
        await call("attach_file", code=f"TASK@{task.code}", **arguments, **{field: value})

    assert await task_file_crud.task_file_list(task.code) == []
    assert await _stored_rows() == 0
    assert await _stored_count(storage) == 0


async def test_a_description_keeps_its_line_breaks_and_tabs(call, task, source):
    attached = await call(
        "attach_file", code=f"TASK@{task.code}", path=str(source), description="одна\nдве\tтри"
    )

    [row] = await task_file_crud.task_file_list(task.code)
    assert row.description == attached["description"] == "одна\nдве\tтри"


async def test_a_file_whose_name_holds_a_control_character_is_refused(call, task, tmp_path, storage):
    odd = tmp_path / "shot\x01\nname.png"
    odd.write_bytes(PNG)

    with pytest.raises(ToolError, match="control character"):
        await call("attach_file", code=f"TASK@{task.code}", path=str(odd))

    assert odd.read_bytes() == PNG
    assert await task_file_crud.task_file_list(task.code) == []
    assert await _stored_rows() == 0


def _the_servers_own_files(tmp_path: Path) -> dict[str, Path]:
    """Files the server must not hand over, directly and through a link that hides them."""
    from src.core.app_path import project_root

    runtime_file = project_root() / "runtime" / "test" / "tmp" / f"secret-{tmp_path.name}.txt"
    runtime_file.parent.mkdir(parents=True, exist_ok=True)
    runtime_file.write_text("the installation's own\n", encoding="utf-8")
    env_file = project_root() / ".env.example.dev"
    hidden = tmp_path / "innocent.txt"
    hidden.symlink_to("/proc/self/environ")
    hidden_env = tmp_path / "settings.txt"
    hidden_env.symlink_to(env_file)
    return {
        "proc": Path("/proc/self/environ"),
        "proc-status": Path("/proc/self/status"),
        "sys": Path("/sys/kernel/mm/transparent_hugepage/enabled"),
        "linked-proc": hidden,
        "runtime": runtime_file,
        "env": env_file,
        "linked-env": hidden_env,
    }


@pytest.mark.parametrize(
    "which", ["proc", "proc-status", "sys", "linked-proc", "runtime", "env", "linked-env"]
)
async def test_the_servers_own_files_are_refused_and_nothing_is_written(
    call, task, tmp_path, storage, which
):
    """``/proc``, ``/sys`` and ``/dev`` (a link to them counts as what it points at), this
    installation's ``runtime/`` and its ``.env*`` files are the server's, not the agent's: the
    environment, the database, the keys. The refusal says why, and nothing is stored."""
    own = _the_servers_own_files(tmp_path)
    target = own[which]
    if not target.exists():
        pytest.skip(f"{target} is not on this machine")
    try:
        with pytest.raises(ToolError, match="the server's own"):
            await call("attach_file", code=f"TASK@{task.code}", path=str(target))
    finally:
        own["runtime"].unlink(missing_ok=True)

    assert await task_file_crud.task_file_list(task.code) == []
    assert await _stored_rows() == 0
    assert await _stored_count(storage) == 0


async def test_a_file_next_to_the_installation_that_is_not_its_env_is_attached(call, task, tmp_path):
    """The fence is the installation's secrets, not every file whose name starts with a dot."""
    dotted = tmp_path / ".env.local.notes.md"
    dotted.write_text("# мои заметки\n", encoding="utf-8")

    attached = await call("attach_file", code=f"TASK@{task.code}", path=str(dotted))

    assert attached["code"].startswith("FILE@")


async def test_path_and_file_together_are_refused(call, task, source, storage):
    with pytest.raises(ToolError, match="not both"):
        await call(
            "attach_file", code=f"TASK@{task.code}", path=str(source), file="FILE@0000000000"
        )

    assert await _stored_count(storage) == 0


async def test_a_folder_is_refused(call, task, tmp_path, storage):
    with pytest.raises(ToolError, match="is not a file"):
        await call("attach_file", code=f"TASK@{task.code}", path=str(tmp_path))

    assert await _stored_count(storage) == 0


@pytest.mark.parametrize(
    ("code", "refusal"),
    [
        ("JOURNAL@0000000000", "cannot hold a file"),
        ("WORKSPACE@0000000000", "cannot hold a file"),
        ("FILE@0000000000", "cannot hold a file"),
        ("python/test", "looks like a codex path"),
        ("TASK@0000000000", "TASK@0000000000 does not exist"),
    ],
)
async def test_a_code_that_holds_no_files_is_refused(call, here, source, storage, code, refusal):
    with pytest.raises(ToolError, match=refusal):
        await call("attach_file", code=code, path=str(source))

    assert await _stored_count(storage) == 0


# ── the holders list their files ──────────────────────────────────────────────


async def test_task_get_lists_the_files_by_code_title_and_description_only(
    call, task, source, shot
):
    holder = f"TASK@{task.code}"
    first = await call("attach_file", code=holder, path=str(source), title="Схема")
    second = await call("attach_file", code=holder, path=str(shot), description="экран")

    files = (await call("task_get", task_code=f"TASK@{task.code}"))["files"]

    assert files == [
        {"code": first["code"], "title": "Схема", "description": ""},
        {"code": second["code"], "title": "", "description": "экран"},
    ]


async def test_task_get_leaves_out_a_file_the_file_manager_deleted(call, task, source):
    answer = await call("attach_file", code=f"TASK@{task.code}", path=str(source))
    await file_delete(answer["code"].removeprefix("FILE@"))

    assert (await call("task_get", task_code=f"TASK@{task.code}"))["files"] == []


async def test_codex_get_lists_a_note_s_files_and_leaves_the_key_out_when_none(call, here, shot):
    note = await _codex_note(here.code)
    empty = await codex_note_crud.note_create(
        parent_code=note.codex_code, segment="lint", title="Линт"
    )
    answer = await call("attach_file", code=f"CODEX@{note.code}", path=str(shot), title="Поток")

    targets = [f"CODEX@{note.code}", f"CODEX@{empty.code}", "/python"]
    nodes = (await call("codex_get", targets=targets))["nodes"]

    assert nodes[0]["files"] == [{"code": answer["code"], "title": "Поток", "description": ""}]
    assert "files" not in nodes[1]
    assert "files" not in nodes[2]


# ── file_get ──────────────────────────────────────────────────────────────────


async def test_file_get_says_what_the_file_is_and_where_it_is_held(call, task, here, shot):
    attached = await call("attach_file", code=f"TASK@{task.code}", path=str(shot), title="Экран")
    code = attached["code"].removeprefix("FILE@")
    note = await _codex_note(here.code)
    await codex_files.codex_file_attach_existing(note.code, code, description="поток")

    got = await call("file_get", file_code=f"FILE@{code}")

    stored = (await file_get_many([code]))[code]
    assert {key: got[key] for key in ("code", "insert", "name", "mime", "type", "size")} == {
        "code": f"FILE@{code}",
        "insert": f"IMAGE@{code}",
        "name": "Shot.PNG",
        "mime": "image/png",
        "type": "image",
        "size": stored.size,
    }
    # The download address carries the name shown here, so the file is saved under it.
    assert got["url"].startswith("http://")
    assert got["url"].endswith(f"/storage/public/{code}")
    assert got["download_url"].endswith(f"/storage/public/{code}/download/Shot.PNG")
    assert got["resource"] == f"workbench://file/{code}"
    assert Path(got["path"]).read_bytes() == PNG
    assert got["places"] == [
        {"holder": f"TASK@{task.code}", "title": "Экран", "description": ""},
        {"holder": f"CODEX@{note.code}", "title": "", "description": "поток"},
    ]


async def test_file_get_shows_only_this_workspace_s_places(call, task, shot):
    attached = await call("attach_file", code=f"TASK@{task.code}", path=str(shot))
    code = attached["code"].removeprefix("FILE@")
    elsewhere = await workspace_create(title="Личное")
    foreign = await task_crud.task_create(workspace_code=elsewhere.code, title="Чужая")
    await task_files.task_file_attach_existing(foreign.code, code)

    got = await call("file_get", file_code=f"IMAGE@{code}")

    assert [place["holder"] for place in got["places"]] == [f"TASK@{task.code}"]


async def test_file_get_names_the_file_as_it_came_here_not_in_another_workspace(
    call, task, tmp_path
):
    """The same bytes, deduplicated: brought in elsewhere first as one name, here as another."""
    elsewhere = await workspace_create(title="Личное")
    foreign = await task_crud.task_create(workspace_code=elsewhere.code, title="Чужая")
    bound = await task_file_attach_bytes(
        foreign.code, PNG, filename="acme-contract-2026.png"
    )
    await _brought_earlier(bound.file_code, Owner("TASK", foreign.code))
    notes = tmp_path / "notes.png"
    notes.write_bytes(PNG)
    attached = await call("attach_file", code=f"TASK@{task.code}", path=str(notes))

    got = await call("file_get", file_code=attached["code"])

    assert got["name"] == "notes.png"
    assert got["download_url"].endswith("/download/notes.png")


async def test_file_get_names_a_file_nameless_here_by_its_code(call, task):
    elsewhere = await workspace_create(title="Личное")
    foreign = await task_crud.task_create(workspace_code=elsewhere.code, title="Чужая")
    bound = await task_file_attach_bytes(
        foreign.code, PNG, filename="acme-contract-2026.png"
    )
    await _brought_earlier(bound.file_code, Owner("TASK", foreign.code))
    await task_files.task_file_attach_existing(task.code, bound.file_code, filename="")

    got = await call("file_get", file_code=f"FILE@{bound.file_code}")

    assert got["name"] == f"{bound.file_code}.png"
    # No name here: the download goes out under the code, never under the other workspace's name.
    assert got["download_url"].endswith(f"/storage/public/{bound.file_code}/download")


async def test_file_get_refuses_a_file_held_only_elsewhere_and_one_held_nowhere(call, here):
    elsewhere = await workspace_create(title="Личное")
    foreign = await task_crud.task_create(workspace_code=elsewhere.code, title="Чужая")
    bound = await task_file_attach_bytes(foreign.code, PNG, filename="shot.png")

    with pytest.raises(ToolError, match="is not attached to anything in 'Работа'"):
        await call("file_get", file_code=f"FILE@{bound.file_code}")
    with pytest.raises(ToolError, match="FILE@0000000000 does not exist"):
        await call("file_get", file_code="FILE@0000000000")


# ── the resource ──────────────────────────────────────────────────────────────


async def test_the_resource_shows_a_picture_as_a_picture(mcp, call, task, shot):
    attached = await call("attach_file", code=f"TASK@{task.code}", path=str(shot))
    uri = (await call("file_get", file_code=attached["code"]))["resource"]

    [content] = await mcp.read_resource(uri)

    assert content.mimeType == "image/png"
    assert base64.b64decode(content.blob) == PNG


async def test_the_resource_shows_text_as_text(mcp, call, task, source):
    attached = await call("attach_file", code=f"TASK@{task.code}", path=str(source))

    [content] = await mcp.read_resource(f"workbench://file/{attached['code']}")

    assert content.text == "# Схема\n"


async def test_the_resource_refuses_other_types_with_the_address(mcp, call, task, tmp_path):
    archive = tmp_path / "bundle.zip"
    archive.write_bytes(ZIP)
    attached = await call("attach_file", code=f"TASK@{task.code}", path=str(archive))
    code = attached["code"].removeprefix("FILE@")

    refusal = f"pictures and text only. Download it from .*/storage/public/{code}"
    with pytest.raises(McpError, match=refusal):
        await mcp.read_resource(f"workbench://file/{code}")


async def test_the_resource_refuses_a_file_over_its_ceiling(mcp, call, task, tmp_path, monkeypatch):
    big = tmp_path / "big.txt"
    big.write_text("x" * 64, encoding="utf-8")
    attached = await call("attach_file", code=f"TASK@{task.code}", path=str(big))
    monkeypatch.setattr("src.modules.workbench.resources.RESOURCE_MAX_BYTES", 10)

    with pytest.raises(McpError, match="over the 10 a resource carries"):
        await mcp.read_resource(f"workbench://file/{attached['code'].removeprefix('FILE@')}")


async def test_the_resource_keeps_to_the_workspace(mcp, here):
    elsewhere = await workspace_create(title="Личное")
    foreign = await task_crud.task_create(workspace_code=elsewhere.code, title="Чужая")
    bound = await task_file_attach_bytes(foreign.code, PNG, filename="shot.png")

    with pytest.raises(McpError, match="is not attached to anything in 'Работа'"):
        await mcp.read_resource(f"workbench://file/{bound.file_code}")
    with pytest.raises(McpError, match="does not exist"):
        await mcp.read_resource("workbench://file/0000000000")


# ── interface_open ────────────────────────────────────────────────────────────


async def test_interface_open_shows_the_file_itself(call, task, shot, no_browser):
    attached = await call("attach_file", code=f"TASK@{task.code}", path=str(shot))
    code = attached["code"].removeprefix("FILE@")

    url = (await call("interface_open", code=f"FILE@{code}"))["result"]

    assert url.endswith(f"/storage/public/{code}")
    assert no_browser == [url]


async def test_interface_open_takes_the_image_word_too(call, task, shot, no_browser):
    attached = await call("attach_file", code=f"TASK@{task.code}", path=str(shot))

    url = (await call("interface_open", code=attached["insert"]))["result"]

    assert attached["insert"].startswith("IMAGE@")
    assert no_browser == [url]
    assert url.endswith(f"/storage/public/{attached['code'].removeprefix('FILE@')}")


async def test_interface_open_refuses_a_file_held_elsewhere_or_nowhere(call, here, no_browser):
    elsewhere = await workspace_create(title="Личное")
    foreign = await task_crud.task_create(workspace_code=elsewhere.code, title="Чужая")
    bound = await task_file_attach_bytes(foreign.code, PNG, filename="shot.png")
    left = await file_register_bytes(ZIP, store="public", owner=Owner("TASK", foreign.code))

    with pytest.raises(ToolError, match="is not attached to anything in 'Работа'"):
        await call("interface_open", code=f"FILE@{bound.file_code}")
    with pytest.raises(ToolError, match=f"FILE@{left.code} does not exist"):
        await call("interface_open", code=f"FILE@{left.code}")

    assert no_browser == []
