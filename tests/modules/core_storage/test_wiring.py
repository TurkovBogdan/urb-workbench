"""Is the module actually plugged in: the application list, the scheduler, the settings, the
migration chain. Behaviour tests call the services directly and stay green when the wiring is gone."""

from __future__ import annotations

import pytest

from src.apps.app.modules import build_modules
from src.core.app_factory import create_app
from src.core.config import Config
from src.core.database.migrations import AlembicRunner
from src.core.scheduler.registry import get_registry
from src.core.settings import get_registry as get_settings_registry
from src.modules.core_storage import CoreStorageModule, layout

pytestmark = pytest.mark.pure


def _storage_module() -> CoreStorageModule:
    found = [module for module in build_modules() if isinstance(module, CoreStorageModule)]
    assert len(found) == 1
    return found[0]


def test_the_application_carries_the_module_with_its_stores():
    assert _storage_module().stores == ("public", "private")


def test_the_module_comes_before_the_data_modules():
    names = [module.name for module in build_modules()]
    assert names.index("core_storage") < names.index("workspace")


def test_building_the_app_wires_the_task_the_settings_and_the_layout(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(layout, "_layout", None)

    create_app(modules=build_modules(), config=Config())

    task = get_registry().get("core_storage", "cleanup")
    assert task is not None and task.schedule == "0 * * * *"
    keys = [field.key for field in get_settings_registry().schema("core_storage")]
    assert keys == ["cleanup_after_hours", "cleanup_limit", "max_file_size_mb"]
    assert layout.get_layout().root.name == "storage"


def test_the_migration_chain_is_on_the_version_path():
    locations = AlembicRunner(modules=build_modules())._version_locations()
    assert CoreStorageModule.migrations_dir in locations
    assert sorted(p.name for p in CoreStorageModule.migrations_dir.glob("csm_*.py")) == [
        "csm_001_files.py",
        "csm_002_file_owners.py",
    ]
