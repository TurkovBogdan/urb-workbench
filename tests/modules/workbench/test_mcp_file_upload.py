"""workbench MCP: a file the server cannot reach goes to a one-time upload address.

``attach_file`` with no path, or with a path the server does not see, opens an upload request of
``core_storage_upload`` and answers with a short address and a ready ``curl`` command — nothing is
bound yet. The bytes are then PUT to the address over HTTP — here through the module's real route
on an ASGI app — and the PUT answers with the same shape a direct attach does. When the bytes
come, the holder and the agent's rights are asked again with the request's workspace. The binding
and the storage owner are read back after the PUT; a refusal is checked by what it leaves behind.
"""

from __future__ import annotations

import hashlib
import json
import os
import shlex
import shutil
import subprocess
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import parse_qs, quote, urlsplit

import pytest
from fastapi import FastAPI
from fastmcp.exceptions import ToolError
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from src.core.api import register_exception_handlers
from src.core.config import get_config
from src.core.database import session_scope
from src.core.router.storage import STORAGE_PREFIX
from src.core.utils.date import utc_now
from src.modules.codex.crud import codex as codex_crud
from src.modules.codex.crud import file as codex_file_crud
from src.modules.codex.crud import mount as mount_crud
from src.modules.codex.crud import note as codex_note_crud
from src.modules.core_storage.dto import Owner
from src.modules.core_storage.services.ownership import file_owners
from src.modules.core_storage_upload import settings as upload_settings
from src.modules.core_storage_upload.api import router
from src.modules.core_storage_upload.constants import ROUTER_PREFIX
from src.modules.core_storage_upload.models import CoreStorageUploadRequest
from src.modules.core_storage_upload.services import requests as requests_module
from src.modules.core_storage_upload.services import server_path
from src.modules.tasks.crud import file as task_file_crud
from src.modules.tasks.crud import task as task_crud

from .conftest import SECRETS_KEY

pytestmark = pytest.mark.db

PNG = bytes.fromhex("89504e470d0a1a0a0000000d49484452") + b"\x00" * 64


@pytest.fixture
async def here(call, workspace, storage):
    await call("workspace_use", workspace_code=workspace.code)
    return workspace


@pytest.fixture
async def task(here):
    return await task_crud.task_create(workspace_code=here.code, title="Выпуск")


def _app() -> FastAPI:
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(router, prefix=f"{STORAGE_PREFIX}{ROUTER_PREFIX}")
    return app


@pytest.fixture
async def http():
    async with AsyncClient(transport=ASGITransport(app=_app()), base_url="http://test") as client:
        yield client


def _named(path: str, filename: str) -> str:
    return f"{path}&filename={quote(filename)}"


async def _owners(code: str) -> set[Owner]:
    return {place.owner for place in await file_owners(code)}


async def _names(code: str) -> list[str]:
    return [place.original_filename + place.original_extension for place in await file_owners(code)]


def _stored(storage) -> list[Path]:
    return [path for path in (storage.root / "public").rglob("*") if path.is_file()]


async def test_no_path_answers_with_an_address_and_the_put_attaches_the_file(
    call, task, http, storage
):
    answer = await call("attach_file", code=f"TASK@{task.code}", title="Экран", description="вход")

    upload = answer["upload"]
    assert set(answer) == {"workspace", "workspace_title", "upload"}
    assert upload["url"].startswith("http://") and upload["url"].endswith(upload["path"])
    assert upload["path"].startswith("/storage/upload?token=")
    assert upload["expires_at"]
    assert upload["command"] == f"curl -T '<local file>' {shlex.quote(upload['url'])}"
    assert await task_file_crud.task_file_list(task.code) == []
    assert _stored(storage) == []

    response = await http.put(_named(upload["path"], "вход.png"), content=PNG)

    assert response.status_code == 200, response.text
    code = response.json()["code"].removeprefix("FILE@")
    assert response.json() == {
        "workspace": answer["workspace"],
        "workspace_title": "Работа",
        "code": f"FILE@{code}",
        "insert": f"IMAGE@{code}",
        "title": "Экран",
        "description": "вход",
    }
    [row] = await task_file_crud.task_file_list(task.code)
    assert (row.file_code, row.title, row.description) == (code, "Экран", "вход")
    assert await _owners(code) == {Owner("TASK", task.code)}
    assert await _names(code) == ["вход.png"]
    assert list(storage.tmp.glob("*")) == []


async def test_the_answer_carries_no_secret_and_the_address_no_data(
    call, task, monkeypatch: pytest.MonkeyPatch
):
    """The model gets a short address and the command only: neither the installation's key nor
    the MCP token, and none of what it asked for rides in the address — the request is in the
    base, under the sha256 of the address's token."""
    monkeypatch.setenv("MCP_TOKEN", "mcp-token-under-test-1234567890")
    get_config.cache_clear()

    answer = await call("attach_file", code=f"TASK@{task.code}", title="Секретный план")

    text = json.dumps(answer, ensure_ascii=False)
    assert get_config().mcp_token == "mcp-token-under-test-1234567890"
    for secret in (SECRETS_KEY, get_config().mcp_token):
        assert secret and secret not in text
    token = parse_qs(urlsplit(answer["upload"]["url"]).query)["token"][0]
    assert set(answer["upload"]["url"].split("?")[1].split("&")) == {f"token={token}"}
    assert "Секретный план" not in text and task.code not in answer["upload"]["url"]
    async with session_scope() as s:
        [stored] = (await s.execute(select(CoreStorageUploadRequest))).scalars().all()
    assert stored.token_hash == hashlib.sha256(token.encode()).hexdigest() != token
    assert (stored.holder, stored.payload) == (
        f"TASK@{task.code}", {"title": "Секретный план", "description": ""}
    )


async def test_a_path_the_server_does_not_see_names_the_file_and_the_command(call, task, http):
    missing = "/elsewhere/on/another machine/отчёт.md"

    upload = (await call("attach_file", code=f"TASK@{task.code}", path=missing))["upload"]

    assert upload["command"] == f"curl -T {shlex.quote(missing)} {shlex.quote(upload['url'])}"
    response = await http.put(upload["path"], content="# Отчёт\n".encode())
    code = response.json()["code"].removeprefix("FILE@")
    assert response.json()["insert"] == f"FILE@{code}"
    assert await _names(code) == ["отчёт.md"]


async def test_a_relative_path_is_the_agent_s_and_goes_through_an_upload(call, task, http):
    upload = (await call("attach_file", code=f"TASK@{task.code}", path="docs/schema.md"))["upload"]

    assert upload["command"].startswith("curl -T docs/schema.md ")
    response = await http.put(upload["path"], content=b"# schema\n")
    assert await _names(response.json()["code"].removeprefix("FILE@")) == ["schema.md"]


async def test_the_address_is_one_time(call, task, http, storage):
    upload = (await call("attach_file", code=f"TASK@{task.code}", title="Экран"))["upload"]

    first = await http.put(upload["path"], content=PNG)
    again = await http.put(upload["path"], content=b"other bytes")

    assert first.status_code == 200
    assert (again.status_code, again.json()["code"]) == (404, "core_storage_upload.request.not_found")
    assert len(await task_file_crud.task_file_list(task.code)) == 1
    assert len(_stored(storage)) == 1


async def test_a_request_outlives_a_restart_of_the_backend(call, task, storage):
    """Nothing is kept in memory: a fresh app takes the request the old one opened."""
    upload = (await call("attach_file", code=f"TASK@{task.code}"))["upload"]

    async with AsyncClient(transport=ASGITransport(app=_app()), base_url="http://test") as fresh:
        response = await fresh.put(upload["path"], content=b"after the restart\n")

    assert response.status_code == 200, response.text
    assert len(await task_file_crud.task_file_list(task.code)) == 1


async def test_an_expired_request_is_404_before_the_body(call, task, http, storage, monkeypatch):
    upload = (await call("attach_file", code=f"TASK@{task.code}"))["upload"]
    later = utc_now() + timedelta(minutes=15)
    monkeypatch.setattr(requests_module, "utc_now", lambda: later)

    response = await http.put(upload["path"], content=PNG)

    assert response.status_code == 404
    assert response.json()["code"] == "core_storage_upload.request.not_found"
    assert await task_file_crud.task_file_list(task.code) == []
    assert _stored(storage) == []


async def test_a_refusal_known_up_front_issues_no_address_and_writes_nothing(call, task, storage):
    with pytest.raises(ToolError, match="File title"):
        await call("attach_file", code=f"TASK@{task.code}", title="я" * 257)

    assert await task_file_crud.task_file_list(task.code) == []
    assert _stored(storage) == []


async def test_a_name_the_storage_cannot_keep_issues_no_address(call, task):
    with pytest.raises(ToolError):
        await call("attach_file", code=f"TASK@{task.code}", path=f"{'я' * 300}.md")


async def test_a_holder_refused_up_front_issues_no_address(call, here):
    codex = await codex_crud.codex_create(segment="python", title="Python")
    await mount_crud.mount_add(codex.code, here.code, agent_can_edit=False)
    note = await codex_note_crud.note_create(parent_code=codex.code, segment="test", title="Тесты")

    with pytest.raises(ToolError, match="not editable for you"):
        await call("attach_file", code=f"CODEX@{note.code}")


async def test_a_write_right_lost_before_the_put_binds_nothing(call, here, http, storage):
    codex = await codex_crud.codex_create(segment="python", title="Python")
    await mount_crud.mount_add(codex.code, here.code, agent_can_edit=True)
    note = await codex_note_crud.note_create(parent_code=codex.code, segment="test", title="Тесты")
    upload = (await call("attach_file", code=f"CODEX@{note.code}"))["upload"]
    await mount_crud.mount_set_agent_can_edit(codex.code, here.code, False)

    response = await http.put(upload["path"], content=PNG)

    assert response.status_code == 403
    assert "not editable for you" in response.json()["error"]
    assert await codex_file_crud.codex_file_list(note.code) == []
    assert _stored(storage) == []
    assert list(storage.tmp.glob("*")) == []


async def test_a_mount_taken_away_before_the_put_binds_nothing(call, here, http, storage):
    codex = await codex_crud.codex_create(segment="python", title="Python")
    await mount_crud.mount_add(codex.code, here.code, agent_can_edit=True)
    note = await codex_note_crud.note_create(parent_code=codex.code, segment="test", title="Тесты")
    upload = (await call("attach_file", code=f"CODEX@{note.code}"))["upload"]
    await mount_crud.mount_remove(codex.code, here.code)

    response = await http.put(upload["path"], content=PNG)

    assert response.status_code == 403
    assert await codex_file_crud.codex_file_list(note.code) == []
    assert _stored(storage) == []


async def test_a_task_deleted_before_the_put_binds_nothing(call, task, http, storage):
    upload = (await call("attach_file", code=f"TASK@{task.code}"))["upload"]
    await task_crud.task_delete(task.code)

    response = await http.put(upload["path"], content=PNG)

    assert response.status_code == 409
    assert "is deleted" in response.json()["error"]
    assert await task_file_crud.task_file_list(task.code) == []
    assert _stored(storage) == []


async def test_a_task_purged_before_the_put_binds_nothing(call, task, http, storage):
    upload = (await call("attach_file", code=f"TASK@{task.code}"))["upload"]
    await task_crud.task_delete(task.code, hard=True)

    response = await http.put(upload["path"], content=PNG)

    assert response.status_code == 404
    assert response.json()["code"] == "tasks.task.not_found"
    assert _stored(storage) == []


async def test_the_upload_lands_in_a_codex_note(call, here, http):
    codex = await codex_crud.codex_create(segment="python", title="Python")
    await mount_crud.mount_add(codex.code, here.code, agent_can_edit=True)
    note = await codex_note_crud.note_create(parent_code=codex.code, segment="test", title="Тесты")
    upload = (await call("attach_file", code=f"CODEX@{note.code}", title="Поток"))["upload"]

    response = await http.put(upload["path"], content=PNG)

    code = response.json()["code"].removeprefix("FILE@")
    assert [row.file_code for row in await codex_file_crud.codex_file_list(note.code)] == [code]
    assert await _owners(code) == {Owner("CODEX", note.code)}
    assert response.json()["title"] == "Поток"


async def test_a_file_the_server_reaches_is_attached_at_once(call, task, tmp_path: Path):
    source = tmp_path / "schema.md"
    source.write_text("# schema\n", encoding="utf-8")

    answer = await call("attach_file", code=f"TASK@{task.code}", path=str(source))

    assert "upload" not in answer
    assert len(await task_file_crud.task_file_list(task.code)) == 1


# ── paths the server cannot use ───────────────────────────────────────────────

# Root reads through any mode, so a permission test proves nothing under it.
needs_permissions = pytest.mark.skipif(os.geteuid() == 0, reason="root ignores file modes")


@pytest.fixture
def locked(tmp_path: Path):
    """A folder the server's user may not enter, with a picture inside; its mode is given back so
    ``tmp_path`` can be cleaned."""
    folder = tmp_path / "locked"
    folder.mkdir()
    (folder / "shot.png").write_bytes(PNG)
    folder.chmod(0)
    yield folder
    folder.chmod(0o700)


@needs_permissions
async def test_a_path_in_a_folder_the_server_may_not_enter_goes_through_an_upload(
    call, task, http, storage, locked
):
    path = str(locked / "shot.png")

    upload = (await call("attach_file", code=f"TASK@{task.code}", path=path))["upload"]

    assert upload["command"] == f"curl -T {shlex.quote(path)} {shlex.quote(upload['url'])}"
    assert await task_file_crud.task_file_list(task.code) == []
    assert _stored(storage) == []
    response = await http.put(upload["path"], content=PNG)
    assert await _names(response.json()["code"].removeprefix("FILE@")) == ["shot.png"]


@needs_permissions
async def test_a_file_the_server_sees_and_may_not_read_is_refused_and_nothing_is_written(
    call, task, storage, tmp_path: Path
):
    sealed = tmp_path / "sealed.png"
    sealed.write_bytes(PNG)
    sealed.chmod(0)

    try:
        with pytest.raises(ToolError, match="cannot read it"):
            await call("attach_file", code=f"TASK@{task.code}", path=str(sealed))
    finally:
        sealed.chmod(0o600)

    assert await task_file_crud.task_file_list(task.code) == []
    assert _stored(storage) == []
    assert sealed.read_bytes() == PNG


async def test_a_read_failing_midway_is_refused_and_nothing_is_written(
    call, task, storage, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    source = tmp_path / "schema.md"
    source.write_text("# schema\n", encoding="utf-8")

    async def failing(handle):
        yield b"# sch"
        raise OSError(5, "Input/output error")

    monkeypatch.setattr(server_path, "_chunks_of", failing)

    with pytest.raises(ToolError, match="server failed on the file \\(Input/output error\\)"):
        await call("attach_file", code=f"TASK@{task.code}", path=str(source))

    assert await task_file_crud.task_file_list(task.code) == []
    assert _stored(storage) == []
    assert list(storage.tmp.glob("*")) == []
    assert source.read_text(encoding="utf-8") == "# schema\n"


async def test_the_home_of_a_user_the_server_does_not_know_goes_through_an_upload(call, task, http):
    path = "~no-such-user-zz/shots/a.png"

    upload = (await call("attach_file", code=f"TASK@{task.code}", path=path))["upload"]

    assert upload["command"] == f"curl -T {path} {shlex.quote(upload['url'])}"
    response = await http.put(upload["path"], content=PNG)
    assert await _names(response.json()["code"].removeprefix("FILE@")) == ["a.png"]


@pytest.mark.skipif(shutil.which("bash") is None, reason="needs a shell to expand the command")
async def test_the_command_leaves_the_home_to_the_agent_s_shell(
    call, task, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """The server's home has no such file, so an address is issued; the agent's shell expands
    ``~``."""
    monkeypatch.setenv("HOME", str(tmp_path / "server-home"))

    upload = (await call("attach_file", code=f"TASK@{task.code}", path="~/my shots/a b.png"))[
        "upload"
    ]

    echoed = upload["command"].replace("curl", "printf '%s\\n'", 1)
    printed = subprocess.run(
        ["bash", "-c", echoed],
        env={"HOME": "/home/agent", "PATH": os.environ.get("PATH", "")},
        capture_output=True,
        text=True,
        check=True,
    ).stdout.splitlines()
    assert printed == ["-T", "/home/agent/my shots/a b.png", upload["url"]]


# ── the upload module's settings ──────────────────────────────────────────────


class _UploadSettings:
    def __init__(self, *, request_ttl_minutes: int = 15, server_path_enabled: bool = True) -> None:
        self.request_ttl_minutes = request_ttl_minutes
        self.server_path_enabled = server_path_enabled


async def test_a_server_that_reads_no_path_answers_a_readable_one_with_an_address(
    call, task, http, storage, tmp_path: Path
):
    """Off, the server's disk is out of reach: the same answer as for a path it cannot see, and
    the file stays unread until the bytes come."""
    source = tmp_path / "schema.md"
    source.write_text("# schema\n", encoding="utf-8")
    upload_settings.set_current(_UploadSettings(server_path_enabled=False))

    upload = (await call("attach_file", code=f"TASK@{task.code}", path=str(source)))["upload"]

    assert upload["command"] == f"curl -T {shlex.quote(str(source))} {shlex.quote(upload['url'])}"
    assert await task_file_crud.task_file_list(task.code) == []
    assert _stored(storage) == []
    response = await http.put(upload["path"], content=b"# sent\n")
    assert await _names(response.json()["code"].removeprefix("FILE@")) == ["schema.md"]


async def test_a_server_that_reads_no_path_does_not_name_its_own_files_either(call, task):
    upload_settings.set_current(_UploadSettings(server_path_enabled=False))

    answer = await call("attach_file", code=f"TASK@{task.code}", path="/proc/self/environ")

    assert "upload" in answer


async def test_the_request_lives_as_long_as_the_setting_says_when_it_is_opened(call, task):
    upload_settings.set_current(_UploadSettings(request_ttl_minutes=1))

    upload = (await call("attach_file", code=f"TASK@{task.code}"))["upload"]

    expires = datetime.strptime(upload["expires_at"], "%Y-%m-%d %H:%M:%S")
    assert expires - utc_now() <= timedelta(minutes=1)
    assert expires - utc_now() > timedelta(seconds=50)
