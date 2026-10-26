"""``core_storage`` fixtures: a storage layout in a temp folder, default settings, a fresh DB.

The layout and the settings are module-level state of the storage; every test gets its own
temp root and the defaults, so nothing leaks between tests or into ``runtime/``.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest
from sqlalchemy import update

from src.core.config import Config
from src.core.database import close_database, init_database, write_scope
from src.modules.core_storage import layout as layout_module
from src.modules.core_storage import settings as settings_module
from src.modules.core_storage.dto import Owner
from src.modules.core_storage.layout import StorageLayout
from src.modules.core_storage.models import CoreStorageFile, CoreStorageFileOwner
from src.modules.core_storage.services.ownership import file_owners

STORES = ("public", "private")


@pytest.fixture
def storage(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> StorageLayout:
    layout = StorageLayout(tmp_path / "storage", tmp_path / "tmp", STORES)
    layout.ensure_dirs()
    monkeypatch.setattr(layout_module, "_layout", layout)
    return layout


@pytest.fixture(autouse=True)
def _default_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings_module, "_current", None)


@pytest.fixture
async def db(config: Config, storage: StorageLayout):
    engine = await init_database(config)
    from src.core.database.runtime import Base
    import src.modules.core_storage.models  # noqa: F401 — registers the storage tables

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    try:
        yield storage
    finally:
        await close_database()


class Settings:
    """A stand-in for the settings store the core hands to ``on_settings_change``."""

    def __init__(self, *, cleanup_after_hours: int = 48, cleanup_limit: int = 0, max_file_size_mb: int = 128):
        self.cleanup_after_hours = cleanup_after_hours
        self.cleanup_limit = cleanup_limit
        self.max_file_size_mb = max_file_size_mb


async def mark_deleted_at(code: str, at: datetime) -> None:
    """Back-date a file's deletion mark — the cleanup only looks at marks older than the term."""
    async with write_scope() as s:
        await s.execute(update(CoreStorageFile).where(CoreStorageFile.code == code).values(deleted_at=at))


async def back_date_owner(code: str, owner: Owner, at: datetime) -> None:
    """Back-date when a place took the file — a reconciliation only looks at places older than
    its grace period."""
    async with write_scope() as s:
        await s.execute(
            update(CoreStorageFileOwner)
            .where(
                CoreStorageFileOwner.file_code == code,
                CoreStorageFileOwner.owner_type == owner.type,
                CoreStorageFileOwner.owner_id == owner.id,
                CoreStorageFileOwner.owner_key == owner.key,
            )
            .values(created_at=at)
        )


def temp_leftovers(layout: StorageLayout) -> list[Path]:
    return sorted(layout.tmp.glob("*")) if layout.tmp.exists() else []


async def owners_of(code: str, *, include_deleted: bool = False) -> list[Owner]:
    """Who holds the file, as the triples ``file_release`` takes."""
    return [place.owner for place in await file_owners(code, include_deleted=include_deleted)]


async def names_of(code: str, *, include_deleted: bool = False) -> dict[Owner, tuple[str, str]]:
    """Each owner's ``(original_filename, original_extension)`` of the file."""
    return {
        place.owner: (place.original_filename, place.original_extension)
        for place in await file_owners(code, include_deleted=include_deleted)
    }
