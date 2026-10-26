"""Is the module actually plugged in — the application list, the zone, the settings, the access log
— and does it keep to its boundary. Behaviour tests use the router directly and stay green when
the wiring is gone."""

from __future__ import annotations

import logging
import re
from pathlib import Path

import pytest
from fastapi import FastAPI

from src.apps.app.modules import build_modules
from src.core.app_factory import create_app
from src.core.config import Config
from src.modules.core_storage_upload import CoreStorageUploadModule
from src.modules.core_storage_upload.access_log import ACCESS_LOGGER, RedactUploadTokens
from src.modules.core_storage_upload.settings import SETTINGS_SCHEMA

pytestmark = pytest.mark.pure

_PACKAGE = Path(__file__).resolve().parents[3] / "src" / "modules" / "core_storage_upload"
_IMPORT = re.compile(r"^\s*(?:from|import)\s+(src\.[\w.]+)", re.MULTILINE)


def test_the_version_is_kept_in_the_class_and_the_module_doc():
    assert CoreStorageUploadModule.version == "1.0.0"
    assert "Version: `1.0.0`" in (_PACKAGE / "MODULE.md").read_text(encoding="utf-8")


def test_the_module_comes_after_the_storage_and_before_the_serving_and_the_data_modules():
    names = [module.name for module in build_modules()]

    assert names.index("core_storage_upload") == names.index("core_storage") + 1
    assert names.index("core_storage_upload") < names.index("core_storage_view")
    assert names.index("core_storage_upload") < names.index("tasks")


def test_the_assembled_app_takes_uploads_at_one_address_and_nowhere_else():
    app = create_app(modules=build_modules(), config=Config())

    routes = {(route.path, method) for route in app.routes for method in getattr(route, "methods", ())}
    assert ("/storage/upload", "POST") in routes
    assert ("/storage/upload", "PUT") in routes
    # An import's archive is not a stored file: it waits in ``tmp/transfer`` for its plan, and its
    # files reach the storage only when the import is applied (``core_transfer``). Those routes are
    # named here one by one, so that any other upload address still fails this test.
    transfer = {
        f"/internal/{zone}/transfer/{step}"
        for zone in ("workbench", "codex")
        for step in ("upload", "{upload_id}/analyze", "{upload_id}/apply")
    }
    uploads = sorted(
        path for path, method in routes if method in ("POST", "PUT") and "upload" in path and path not in transfer
    )
    assert uploads == ["/storage/upload", "/storage/upload"]
    assert not any(path.endswith("/files") and method == "POST" for path, method in routes)


def test_the_module_shows_its_settings_on_the_settings_page():
    module = next(m for m in build_modules() if m.name == "core_storage_upload")

    assert module.settings_schema is SETTINGS_SCHEMA


def test_configure_keeps_the_token_out_of_the_access_log(monkeypatch: pytest.MonkeyPatch):
    logger = logging.getLogger(ACCESS_LOGGER)
    monkeypatch.setattr(logger, "filters", [])

    CoreStorageUploadModule().configure(FastAPI(), Config())

    assert any(isinstance(f, RedactUploadTokens) for f in logger.filters)


def test_configure_schedules_the_cleanup_of_expired_requests():
    from src.core.scheduler.registry import get_registry
    from src.modules.core_storage_upload.tasks.cleanup_task import RequestCleanupTask

    CoreStorageUploadModule().configure(FastAPI(), Config())
    CoreStorageUploadModule().configure(FastAPI(), Config())

    entry = get_registry().get(RequestCleanupTask.MODULE, RequestCleanupTask.CODE)
    assert entry is not None
    assert (RequestCleanupTask.SCHEDULE, RequestCleanupTask.TTL) == ("10 * * * *", 600)


def test_the_module_keeps_its_own_migration_chain():
    assert CoreStorageUploadModule.migrations_dir == _PACKAGE / "migrations" / "versions"
    assert [path.name for path in sorted(CoreStorageUploadModule.migrations_dir.glob("csu_*.py"))] == [
        "csu_001_request.py"
    ]


def test_the_module_imports_only_the_core_and_the_storage():
    imported = {
        target
        for path in _PACKAGE.rglob("*.py")
        for target in _IMPORT.findall(path.read_text(encoding="utf-8"))
    }
    outside = {
        target
        for target in imported
        if not target.startswith(
            ("src.core", "src.modules.core_storage_upload", "src.modules.core_storage.")
        )
    }

    assert any(target.startswith("src.modules.core_storage.") for target in imported)  # positive control
    assert outside == set()

