"""The module itself: its version, its store list, its wiring into the application."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI

from src.core.config import Config
from src.core.scheduler.registry import get_registry
from src.modules.core_storage import CoreStorageModule
from src.modules.core_storage import layout as layout_module
from src.modules.core_storage import settings
from src.modules.core_storage.dto import Owner
from src.modules.core_storage.errors import InvalidStores
from src.modules.core_storage.services.registration import file_register_bytes

from .conftest import Settings

_MODULE_DOC = Path(__file__).resolve().parents[3] / "src" / "modules" / "core_storage" / "MODULE.md"


@pytest.mark.pure
def test_the_version_is_kept_in_the_class_and_the_module_doc():
    assert CoreStorageModule.version == "2.6.0"
    assert "Version: `2.6.0`" in _MODULE_DOC.read_text(encoding="utf-8")


@pytest.mark.pure
def test_an_unusable_store_list_stops_the_build():
    with pytest.raises(InvalidStores):
        CoreStorageModule(stores=[])


@pytest.mark.pure
def test_configure_sets_the_layout_from_the_core_paths_and_registers_the_cleanup_once(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(layout_module, "_layout", None)
    registry = get_registry()
    registry.clear()
    module = CoreStorageModule(stores=["public"])
    try:
        module.configure(FastAPI(), Config())
        module.configure(FastAPI(), Config())

        layout = layout_module.get_layout()
        assert layout.root.name == "storage" and layout.tmp.name == "tmp"
        assert layout.stores == ("public",)
        assert registry.get("core_storage", "cleanup") is not None
        assert registry.get("core_storage", "reconcile") is not None
    finally:
        registry.clear()


@pytest.mark.pure
def test_the_storage_root_comes_from_storage_path_when_set(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    """A copy of the database rehearsed elsewhere needs its own bytes too: ``STORAGE_PATH`` points
    the storage at them; unset, the root stays ``runtime/<APP_ENV>/storage``."""
    from src.core.app_path import AppPath

    monkeypatch.setattr(layout_module, "_layout", None)
    registry = get_registry()
    registry.clear()
    module = CoreStorageModule(stores=["public"])
    try:
        module.configure(FastAPI(), Config(_env_file=None, storage_path=str(tmp_path / "copy")))
        assert layout_module.get_layout().root == tmp_path / "copy"

        module.configure(FastAPI(), Config(_env_file=None, storage_path=""))
        assert layout_module.get_layout().root == AppPath.from_root().storage
    finally:
        registry.clear()


@pytest.mark.pure
def test_a_relative_storage_path_is_read_from_the_application_root():
    from src.core.app_path import project_root

    config = Config(_env_file=None, storage_path="rehearsal/storage")

    assert config.storage_root == project_root() / "rehearsal" / "storage"


@pytest.mark.pure
@pytest.mark.parametrize(
    ("db_path", "storage_path", "warned"),
    [
        ("{outside}/copy.sqlite3", "", True),
        ("{outside}/copy.sqlite3", "{outside}/storage", False),
        ("{runtime}/app.sqlite3", "", False),
        ("", "", False),
        (":memory:", "", False),
    ],
    ids=["copy-without-storage", "copy-with-storage", "own-runtime", "default", "in-memory"],
)
def test_a_database_outside_the_profile_without_its_own_storage_is_warned_about(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, db_path: str, storage_path: str, warned: bool
):
    """A database copied elsewhere would share the bytes of the original: a cleanup there removes
    the files the original still holds."""
    from src.core.app_path import resolve_runtime_root
    from src.modules.core_storage import module as module_file

    recorder = _Recorder()
    monkeypatch.setattr(module_file, "_LOG", recorder)
    monkeypatch.setattr(layout_module, "_layout", None)
    places = {"outside": str(tmp_path), "runtime": str(resolve_runtime_root())}
    config = Config(
        _env_file=None,
        db_provider="sqlite",
        db_path=db_path.format(**places),
        storage_path=storage_path.format(**places),
    )
    registry = get_registry()
    registry.clear()
    try:
        CoreStorageModule(stores=["public"]).configure(FastAPI(), config)
    finally:
        registry.clear()

    assert bool([w for w in recorder.warnings if "STORAGE_PATH" in w]) is warned
    # The same condition keeps the hourly reconciliation from removing anything on that root.
    assert layout_module.get_layout().root_shared is warned


@pytest.mark.pure
def test_settings_changes_reach_the_services():
    CoreStorageModule(stores=["public"]).on_settings_change(Settings(cleanup_limit=7))
    assert settings.cleanup_limit() == 7


class _Recorder:
    def __init__(self) -> None:
        self.warnings: list[str] = []

    def warning(self, message: str, *args) -> None:
        self.warnings.append(message % args)


@pytest.mark.db
async def test_startup_creates_the_store_folders_and_names_stores_off_the_list(
    db, monkeypatch: pytest.MonkeyPatch
):
    from src.modules.core_storage import module as module_file

    await file_register_bytes(b"x", store="private", owner=Owner("task", "7DB4F6E0DE"))
    recorder = _Recorder()
    monkeypatch.setattr(module_file, "_LOG", recorder)
    monkeypatch.setattr(
        layout_module, "_layout", layout_module.StorageLayout(db.root / "fresh", db.tmp, ["public"])
    )

    await CoreStorageModule(stores=["public"]).on_startup(FastAPI())

    assert (db.root / "fresh" / "public").is_dir()
    assert len(recorder.warnings) == 1 and "private" in recorder.warnings[0]


@pytest.mark.db
async def test_startup_is_quiet_when_every_store_is_listed(db, monkeypatch: pytest.MonkeyPatch):
    from src.modules.core_storage import module as module_file

    await file_register_bytes(b"x", store="public", owner=Owner("task", "7DB4F6E0DE"))
    recorder = _Recorder()
    monkeypatch.setattr(module_file, "_LOG", recorder)

    await CoreStorageModule(stores=["public", "private"]).on_startup(FastAPI())

    assert recorder.warnings == []
