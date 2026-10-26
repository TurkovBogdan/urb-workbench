"""Is the module actually plugged in — the application list, the zone — and does it keep to its
boundary. Behaviour tests use the router directly and stay green when the wiring is gone."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from src.apps.app.modules import build_modules
from src.core.app_factory import create_app
from src.core.config import Config
from src.modules.core_storage_view import CoreStorageViewModule
from src.modules.core_storage_view.constants import LOG_CHANNEL

pytestmark = pytest.mark.pure

_PACKAGE = Path(__file__).resolve().parents[3] / "src" / "modules" / "core_storage_view"
_IMPORT = re.compile(r"^\s*(?:from|import)\s+(src\.[\w.]+)", re.MULTILINE)
_LOGGER = re.compile(r"get_logger\(([^)]*)\)")


def test_the_version_is_kept_in_the_class_and_the_module_doc():
    assert CoreStorageViewModule.version == "2.1.0"
    assert "Version: `2.1.0`" in (_PACKAGE / "MODULE.md").read_text(encoding="utf-8")


def test_the_module_comes_after_the_storage_and_its_upload_and_before_the_data_modules():
    names = [module.name for module in build_modules()]
    assert names.index("core_storage_view") == names.index("core_storage_upload") + 1
    assert names.index("core_storage_view") > names.index("core_storage")
    assert names.index("core_storage_view") < names.index("workspace")


def test_the_assembled_app_serves_the_route_under_the_storage_zone_and_takes_nothing_in():
    app = create_app(modules=build_modules(), config=Config())

    view = [
        (route.path, method)
        for route in app.routes
        for method in getattr(route, "methods", ())
        if getattr(route, "endpoint", None) is not None
        and route.endpoint.__module__.startswith("src.modules.core_storage_view")
    ]
    assert sorted(view) == [
        (path, method)
        for path in (
            "/storage/{store}/{code}",
            "/storage/{store}/{code}/download",
            "/storage/{store}/{code}/download/{name}",
        )
        for method in ("GET", "HEAD")
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
        if not target.startswith(("src.core", "src.modules.core_storage_view", "src.modules.core_storage."))
    }

    assert any(target.startswith("src.modules.core_storage.") for target in imported)  # positive control
    assert outside == set()


def test_every_logger_of_the_module_takes_the_channel_constant():
    found = {
        path.name: _LOGGER.findall(path.read_text(encoding="utf-8"))
        for path in _PACKAGE.rglob("*.py")
    }
    calls = {name: args for name, args in found.items() if args}

    assert calls  # positive control: the sweep reached a file that logs
    assert {name: args for name, args in calls.items() if args != ["LOG_CHANNEL"]} == {}
    assert LOG_CHANNEL == "core_storage_view"
