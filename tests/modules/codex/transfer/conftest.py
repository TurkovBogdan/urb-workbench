"""Codex transfer fixtures: a base with every table, a codex «with everything», another
installation to import into.

``rich_codex`` holds all four levels, a record in the bin (with a file of its own), files on
records of different levels, one file two records share, rules and texts that refer to records
and files, and a reference out of the archive.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from src.core.api import register_exception_handlers
from src.core.config import Config
from src.core.database import close_database, init_database
from src.modules.codex.api import router
from src.modules.codex.crud import codex as codex_crud
from src.modules.codex.crud import mount as mount_crud
from src.modules.codex.crud import note as note_crud
from src.modules.core_storage import layout as storage_layout
from src.modules.core_storage import settings as storage_settings
from src.modules.core_storage.layout import StorageLayout
from src.modules.core_transfer import uploads
from src.modules.workspace.crud.workspace import workspace_create

from ..file_support import codex_file_attach_bytes

PNG = bytes.fromhex("89504e470d0a1a0a0000000d49484452") + b"\x00" * 64


async def _schema(config: Config) -> None:
    engine = await init_database(config)
    from src.core.database.runtime import Base
    import src.core.models  # noqa: F401
    import src.modules.codex.models  # noqa: F401
    import src.modules.workspace.models  # noqa: F401

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


def _layout(root: Path, monkeypatch: pytest.MonkeyPatch) -> StorageLayout:
    layout = StorageLayout(root / "storage", root / "tmp", ("public", "private"))
    layout.ensure_dirs()
    monkeypatch.setattr(storage_layout, "_layout", layout)
    monkeypatch.setattr(storage_settings, "_current", None)
    return layout


@pytest.fixture(autouse=True)
def transfer_folder(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "transfer"
    monkeypatch.setattr(uploads, "transfer_root", lambda: root)
    return root


@pytest.fixture
def storage(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> StorageLayout:
    return _layout(tmp_path / "first", monkeypatch)


@pytest.fixture
async def db(config: Config, storage: StorageLayout):
    await _schema(config)
    try:
        yield storage
    finally:
        await close_database()


@pytest.fixture
async def client(db):
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(router, prefix="/internal/codex")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


@pytest.fixture
def other_installation(config: Config, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    async def move() -> StorageLayout:
        await close_database()
        layout = _layout(tmp_path / "second", monkeypatch)
        await _schema(config)
        return layout

    return move


@dataclass
class RichCodex:
    workspace: str
    codex: str
    top: str
    second: str
    third: str
    fourth: str
    sibling: str
    binned: str
    image: str
    deep_file: str
    shared_file: str
    binned_file: str


async def make_rich_codex(segment: str = "python", workspace_title: str = "Работа") -> RichCodex:
    workspace = (await workspace_create(title=workspace_title)).code
    codex = (await codex_crud.codex_create(segment=segment, title="Python", description="когда читать")).code
    await mount_crud.mount_add(codex, workspace)
    top = (await note_crud.note_create(parent_code=codex, segment="test", title="Тесты")).code
    second = (await note_crud.note_create(parent_code=top, segment="fixtures", title="Фикстуры")).code
    third = (await note_crud.note_create(parent_code=second, segment="factories", title="Фабрики")).code
    fourth = (await note_crud.note_create(parent_code=codex, segment="style", title="Стиль")).code
    sibling = (await note_crud.note_create(parent_code=top, segment="markers", title="Маркеры")).code
    binned = (await note_crud.note_create(parent_code=top, segment="old", title="Устаревшее")).code

    image = (await codex_file_attach_bytes(top, PNG, filename="shot.png", title="Скриншот")).file_code
    deep_file = (await codex_file_attach_bytes(third, b"deep bytes", filename="a.txt")).file_code
    shared_file = (await codex_file_attach_bytes(second, b"shared", filename="s.txt")).file_code
    await codex_file_attach_bytes(fourth, b"shared", filename="s.txt", title="Общий")
    binned_file = (await codex_file_attach_bytes(binned, b"binned bytes", filename="b.txt")).file_code
    await note_crud.note_delete(binned)

    await codex_crud.codex_update(codex, body=f"Правила: см. CODEX@{top}, ![x](IMAGE@{image}), TASK@0123456789")
    await note_crud.note_update(top, body=f"Ниже CODEX@{second} и CODEX@{third}, файл FILE@{deep_file}")
    return RichCodex(
        workspace=workspace, codex=codex, top=top, second=second, third=third, fourth=fourth, sibling=sibling,
        binned=binned, image=image, deep_file=deep_file, shared_file=shared_file, binned_file=binned_file,
    )


@pytest.fixture
async def rich(db) -> RichCodex:
    return await make_rich_codex()
