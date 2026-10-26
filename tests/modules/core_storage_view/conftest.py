"""``core_storage_view`` fixtures: a storage layout in a temp folder, a fresh DB, and an HTTP
client over the module's router.

The layout and the settings are module-level state; every test gets its own, so
nothing leaks between tests or into ``runtime/``.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from src.core.api import register_exception_handlers
from src.core.config import Config
from src.core.database import close_database, init_database
from src.core.router.storage import STORAGE_PREFIX
from src.modules.core_storage import layout as layout_module
from src.modules.core_storage import settings as settings_module
from src.modules.core_storage.layout import StorageLayout
from src.modules.core_storage_view.api import router
from src.modules.core_storage_view.constants import ROUTER_PREFIX

STORES = ("public", "private")


class Settings:
    """A stand-in for the settings store the core hands to ``core_storage``."""

    def __init__(self, *, cleanup_after_hours: int = 48, cleanup_limit: int = 0, max_file_size_mb: int = 128):
        self.cleanup_after_hours = cleanup_after_hours
        self.cleanup_limit = cleanup_limit
        self.max_file_size_mb = max_file_size_mb


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


@pytest.fixture
async def client():
    app = FastAPI()
    register_exception_handlers(app)
    # The prefix mirrors the production one: the zone's, then the module's.
    app.include_router(router, prefix=f"{STORAGE_PREFIX}{ROUTER_PREFIX}")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


def leftovers(folder: Path) -> list[Path]:
    return sorted(folder.glob("*")) if folder.exists() else []
