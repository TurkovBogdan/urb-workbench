"""A file named by its path on the server's disk: read, never moved, and never the server's own.

What the server finds at the path decides the way — taken, refused with the reason, or ``None``
(the client sends the bytes). The server's own files — the kernel's views, the installation's
``runtime/`` and ``.env*`` — are refused whatever the link in between. The agent surface's answers
to each case are tested with it (``tests/modules/workbench/test_mcp_files.py``,
``test_mcp_file_upload.py``).
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from sqlalchemy import func, select

from src.core.app_path import project_root
from src.core.config import get_config
from src.core.database import session_scope
from src.modules.core_storage import settings as storage_settings
from src.modules.core_storage.errors import FileTooLarge
from src.modules.core_storage.models import CoreStorageFile
from src.modules.core_storage.services.ownership import file_owners
from src.modules.core_storage_upload import settings as upload_settings
from src.modules.core_storage_upload.errors import (
    FilenameRefused,
    HolderRefused,
    NotAFile,
    RefusalKind,
    ServersOwnFile,
    UnreadableFile,
)
from src.modules.core_storage_upload.services.server_path import server_file, take_server_file

from .conftest import StorageSettings, UploadSettings, leftovers

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64

# Root reads through any mode, so a permission test proves nothing under it.
needs_permissions = pytest.mark.skipif(os.geteuid() == 0, reason="root ignores file modes")


async def _stored_count() -> int:
    async with session_scope() as s:
        return (await s.execute(select(func.count()).select_from(CoreStorageFile))).scalar_one()


@pytest.mark.pure
async def test_a_readable_file_is_found(tmp_path: Path):
    source = tmp_path / "schema.md"
    source.write_text("# schema\n", encoding="utf-8")

    assert await server_file(str(source)) == source


@pytest.mark.pure
@pytest.mark.parametrize("path", ["docs/schema.md", "/no/such/file.md", "~no-such-user-zz/a.png"])
async def test_a_path_the_server_cannot_see_is_none(path):
    assert await server_file(path) is None


@pytest.mark.pure
async def test_a_folder_is_not_a_file(tmp_path: Path):
    with pytest.raises(NotAFile):
        await server_file(str(tmp_path))


@pytest.mark.pure
@needs_permissions
async def test_a_file_the_server_may_not_open_is_unreadable(tmp_path: Path):
    sealed = tmp_path / "sealed.png"
    sealed.write_bytes(PNG)
    sealed.chmod(0)
    try:
        with pytest.raises(UnreadableFile) as refused:
            await server_file(str(sealed))
    finally:
        sealed.chmod(0o600)

    assert refused.value.reason


@pytest.mark.pure
@needs_permissions
async def test_a_file_behind_a_folder_the_server_may_not_enter_is_none(tmp_path: Path):
    folder = tmp_path / "locked"
    folder.mkdir()
    (folder / "shot.png").write_bytes(PNG)
    folder.chmod(0)
    try:
        assert await server_file(str(folder / "shot.png")) is None
    finally:
        folder.chmod(0o700)


@pytest.mark.pure
async def test_the_server_s_own_files_are_refused_links_followed(tmp_path: Path):
    runtime_file = project_root() / "runtime" / "test" / "tmp" / f"own-{tmp_path.name}.txt"
    runtime_file.parent.mkdir(parents=True, exist_ok=True)
    runtime_file.write_text("the installation's own\n", encoding="utf-8")
    linked = tmp_path / "innocent.txt"
    linked.symlink_to("/proc/self/environ")
    try:
        for path, reason in (
            ("/proc/self/environ", "a system file"),
            ("/proc/self/status", "a system file"),
            (str(linked), "a system file"),
            (str(runtime_file), "the installation's runtime folder"),
            (str(project_root() / ".env.example.dev"), "the installation's settings"),
        ):
            with pytest.raises(ServersOwnFile) as refused:
                await server_file(path)
            assert refused.value.reason == reason
    finally:
        runtime_file.unlink(missing_ok=True)


@pytest.fixture
def data_elsewhere(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """The installation's database and stores moved out of ``runtime/`` by the settings, as
    ``DB_PATH`` and ``STORAGE_PATH`` allow; the copies follow the database."""
    data = tmp_path / "data"
    (data / "storage" / "public").mkdir(parents=True)
    (data / "backups" / "copy-1").mkdir(parents=True)
    monkeypatch.setenv("DB_PROVIDER", "sqlite")
    monkeypatch.setenv("DB_PATH", str(data / "app.sqlite3"))
    monkeypatch.setenv("STORAGE_PATH", str(data / "storage"))
    get_config.cache_clear()
    return data


@pytest.mark.pure
async def test_the_installation_s_data_moved_by_the_settings_is_refused(
    data_elsewhere: Path, tmp_path: Path
):
    from src.core.backup import BACKUP_FOLDER_NAME

    files = {
        data_elsewhere / "app.sqlite3": "the installation's database",
        data_elsewhere / "app.sqlite3-wal": "the installation's database",
        data_elsewhere / "storage" / "public" / "AB12000001.png": "the installation's stored files",
        data_elsewhere / BACKUP_FOLDER_NAME / "app.sqlite3": "the installation's copies",
    }
    for path in files:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(PNG)
    linked = tmp_path / "harmless.png"
    linked.symlink_to(data_elsewhere / "app.sqlite3")
    beside = data_elsewhere / "notes.txt"
    beside.write_text("mine\n", encoding="utf-8")

    for path, reason in [*files.items(), (linked, "the installation's database")]:
        with pytest.raises(ServersOwnFile) as refused:
            await server_file(str(path))
        assert refused.value.reason == reason
    # Positive control: a file of the folder that is none of them is found.
    assert await server_file(str(beside)) == beside


@pytest.mark.db
async def test_a_link_turned_to_the_server_s_own_file_after_the_check_is_refused(
    db, holder, tmp_path: Path
):
    """The path is checked when it is found, and the link on it may be pointed elsewhere before
    the file is opened: the opened file is checked again, and nothing is taken."""
    harmless = tmp_path / "harmless.txt"
    harmless.write_text("harmless\n", encoding="utf-8")
    link = tmp_path / "shot.txt"
    link.symlink_to(harmless)
    source = await server_file(str(link))
    assert source == link

    link.unlink()
    link.symlink_to(project_root() / ".env.example.dev")

    with pytest.raises(ServersOwnFile) as refused:
        await take_server_file("TEST@1", source, payload={})

    assert refused.value.reason == "the installation's settings"
    assert holder.attached == []
    assert await _stored_count() == 0


@pytest.mark.pure
async def test_a_server_that_reads_no_path_sees_none(tmp_path: Path):
    source = tmp_path / "schema.md"
    source.write_text("# schema\n", encoding="utf-8")
    upload_settings.set_current(UploadSettings(server_path_enabled=False))

    assert await server_file(str(source)) is None
    assert await server_file("/proc/self/environ") is None


@pytest.mark.db
async def test_a_file_is_taken_under_its_name_and_left_where_it_is(db, holder, tmp_path: Path):
    source = tmp_path / "report.final.pdf"
    source.write_bytes(b"%PDF-1.4 body")

    asked = {"title": "Отчёт", "description": "итог"}

    attached = await take_server_file("TEST@1", source, payload=asked, workspace="WS1")

    assert source.read_bytes() == b"%PDF-1.4 body"
    assert holder.checks == [("1", asked, "WS1")]
    assert holder.attached == [("1", "report.final.pdf", asked, "WS1")]
    owners = await file_owners(attached.file_code)
    assert [(p.original_filename, p.original_extension) for p in owners] == [
        ("report.final", ".pdf")
    ]
    assert leftovers(db.tmp) == []


@pytest.mark.db
async def test_a_holder_refusal_reads_nothing(db, holder, tmp_path: Path):
    source = tmp_path / "a.txt"
    source.write_text("a", encoding="utf-8")
    holder.refuse_check = HolderRefused("no", kind=RefusalKind.FORBIDDEN)

    with pytest.raises(HolderRefused):
        await take_server_file("TEST@1", source, payload={}, workspace="WS1")

    assert holder.attached == []
    assert await _stored_count() == 0


@pytest.mark.db
async def test_a_file_over_the_ceiling_is_refused_by_its_size_before_it_is_read(
    db, holder, tmp_path: Path
):
    storage_settings.set_current(StorageSettings(max_file_size_mb=1))
    source = tmp_path / "big.bin"
    source.write_bytes(b"0" * (1024 * 1024 + 1))

    with pytest.raises(FileTooLarge):
        await take_server_file("TEST@1", source, payload={})

    assert holder.attached == []
    assert leftovers(db.tmp) == []


@pytest.mark.db
async def test_a_name_with_a_control_character_is_refused_and_the_file_stays(
    db, holder, tmp_path: Path
):
    source = tmp_path / "shot\nname.png"
    source.write_bytes(PNG)

    with pytest.raises(FilenameRefused):
        await take_server_file("TEST@1", source, payload={})

    assert holder.checks == []
    assert source.read_bytes() == PNG
