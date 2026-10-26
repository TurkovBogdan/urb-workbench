"""``core_storage_upload`` fixtures: a storage layout in a temp folder, default settings, a fresh
DB with the storage's tables and the module's, a holder of the tests' own, and an HTTP client over
the module's route.

The layout, the settings, the holders' registry and the upload answer are module-level state;
every test gets its own, so nothing leaks between tests or into ``runtime/``. The holder
``TEST@<id>`` stands for what a consumer module registers: it keeps the file as the owner
``("test", <id>)``, takes its title from the payload and refuses on demand.
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
from src.modules.core_storage import settings as storage_settings
from src.modules.core_storage.dto import Owner, SpooledFile
from src.modules.core_storage.layout import StorageLayout
from src.modules.core_storage.services.registration import file_register_spooled
from src.modules.core_storage_upload import settings as upload_settings
from src.modules.core_storage_upload.api import router
from src.modules.core_storage_upload.constants import ROUTER_PREFIX
from src.modules.core_storage_upload.dto import AttachedFile, UploadHolder
from src.modules.core_storage_upload.errors import AlreadyHeld, HolderRefused
from src.modules.core_storage_upload.services import holders as holders_module
from src.modules.core_storage_upload.services import requests as requests_module

STORES = ("public", "private")
UPLOAD = f"{STORAGE_PREFIX}{ROUTER_PREFIX}/upload"
# The page of the app itself, as the test client's host names it.
OWN_ORIGIN = {"Origin": "http://test"}


class StorageSettings:
    """A stand-in for the settings store the core hands to ``core_storage``."""

    def __init__(self, *, max_file_size_mb: int = 128):
        self.cleanup_after_hours = 48
        self.cleanup_limit = 0
        self.max_file_size_mb = max_file_size_mb


class UploadSettings:
    """A stand-in for the settings store the core hands to this module."""

    def __init__(self, *, request_ttl_minutes: int = 15, server_path_enabled: bool = True):
        self.request_ttl_minutes = request_ttl_minutes
        self.server_path_enabled = server_path_enabled


class TestHolder:
    """``TEST@<id>``: what a consumer registers, with every call remembered and a refusal ready
    to be armed — ``refuse_check`` / ``refuse_attach`` raise as the holder's own rule would."""

    __test__ = False

    def __init__(self) -> None:
        self.checks: list[tuple[str, dict, str | None]] = []
        self.attached: list[tuple[str, str, dict, str | None]] = []
        self.bound: dict[tuple[str, str], AttachedFile] = {}
        self.refuse_check: HolderRefused | None = None
        self.refuse_attach: HolderRefused | None = None

    async def check(self, bare: str, payload, *, workspace: str | None = None) -> None:
        self.checks.append((bare, dict(payload), workspace))
        if self.refuse_check is not None:
            raise self.refuse_check

    async def attach(
        self,
        bare: str,
        spooled: SpooledFile,
        payload,
        *,
        filename: str,
        workspace: str | None = None,
    ) -> AttachedFile:
        self.attached.append((bare, filename, dict(payload), workspace))
        if self.refuse_attach is not None:
            raise self.refuse_attach
        title, description = payload.get("title", ""), payload.get("description", "")
        stored = await file_register_spooled(
            spooled, store="public", owner=Owner("test", bare), filename=filename
        )
        held = self.bound.get((bare, stored.code))
        if held is not None:
            raise AlreadyHeld(
                f"FILE@{stored.code} is in TEST@{bare} already",
                attached=held,
                code="test.file.already_attached",
                params={"file": f"FILE@{stored.code}"},
            )
        attached = AttachedFile(file_code=stored.code, title=title, description=description)
        self.bound[(bare, stored.code)] = attached
        return attached

    async def answer(self, bare: str, attached: AttachedFile) -> dict:
        return {"holder": f"TEST@{bare}", "file": attached.file_code, "title": attached.title}


@pytest.fixture
def storage(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> StorageLayout:
    layout = StorageLayout(tmp_path / "storage", tmp_path / "tmp", STORES)
    layout.ensure_dirs()
    monkeypatch.setattr(layout_module, "_layout", layout)
    return layout


@pytest.fixture(autouse=True)
def _module_state(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(storage_settings, "_current", None)
    monkeypatch.setattr(upload_settings, "_current", None)
    monkeypatch.setattr(requests_module, "_answer", None)


@pytest.fixture(autouse=True)
def holder(monkeypatch: pytest.MonkeyPatch) -> TestHolder:
    keeper = TestHolder()
    monkeypatch.setattr(holders_module, "_holders", {})
    holders_module.register_upload_holder(
        "TEST", UploadHolder(check=keeper.check, attach=keeper.attach, answer=keeper.answer)
    )
    return keeper


@pytest.fixture
async def db(config: Config, storage: StorageLayout):
    engine = await init_database(config)
    from src.core.database.runtime import Base
    import src.modules.core_storage.models  # noqa: F401 — registers the storage tables
    import src.modules.core_storage_upload.models  # noqa: F401 — the upload requests

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    try:
        yield storage
    finally:
        await close_database()


def upload_app() -> FastAPI:
    app = FastAPI()
    register_exception_handlers(app)
    # The prefix mirrors the production one: the zone's, then the module's.
    app.include_router(router, prefix=f"{STORAGE_PREFIX}{ROUTER_PREFIX}")
    return app


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=upload_app()), base_url="http://test") as c:
        yield c


class UnreadBody:
    """A request body that must not be read: a refusal due before the body pulls nothing."""

    def __init__(self) -> None:
        self.pulled = False

    def __aiter__(self):
        return self

    async def __anext__(self) -> bytes:
        self.pulled = True
        raise AssertionError("the body was read before the refusal")


def leftovers(folder: Path) -> list[Path]:
    return sorted(path for path in folder.rglob("*") if path.is_file()) if folder.exists() else []
