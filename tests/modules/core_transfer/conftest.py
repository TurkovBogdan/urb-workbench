"""``core_transfer`` fixtures: a toy archive format, the transfer folder and the storage in temp
folders, a fresh DB with the storage tables and the module state store."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from src.core.config import Config
from src.core.database import close_database, init_database
from src.modules.core_storage import layout as storage_layout
from src.modules.core_storage import settings as storage_settings
from src.modules.core_storage.layout import StorageLayout
from src.modules.core_transfer import uploads
from src.modules.core_transfer.container import ArchiveFormat

FORMAT = ArchiveFormat(
    media_type="application/vnd.uroboros.test+zip",
    name="uroboros.test",
    version=1,
    extension=".tst",
    entries=(
        re.compile(r"rows/items\.jsonl"),
        re.compile(r"texts/[0-9A-F]{10}\.md"),
        re.compile(r"files/[0-9A-F]{10}(\.[a-z0-9]{1,15})?"),
    ),
)


@pytest.fixture(autouse=True)
def transfer_folder(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "transfer"
    monkeypatch.setattr(uploads, "transfer_root", lambda: root)
    return root


@pytest.fixture
def storage(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> StorageLayout:
    layout = StorageLayout(tmp_path / "storage", tmp_path / "tmp", ("public", "private"))
    layout.ensure_dirs()
    monkeypatch.setattr(storage_layout, "_layout", layout)
    monkeypatch.setattr(storage_settings, "_current", None)
    return layout


@pytest.fixture
async def db(config: Config, storage: StorageLayout):
    engine = await init_database(config)
    from src.core.database.runtime import Base
    import src.core.models  # noqa: F401 — the module state store
    import src.modules.core_storage.models  # noqa: F401 — the storage tables

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    try:
        yield storage
    finally:
        await close_database()
