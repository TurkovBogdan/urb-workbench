"""The ``core_storage`` module — registration and physical storage of files.

A platform module: like every ``core_*`` module it sits under the application levels, imports no
application module and is known by its consumers, never the other way round. It takes a file in
any form, keeps its bytes in one of the stores it was given, stores one content once per store,
counts who holds a file and removes the files nobody holds after a configured term. For every
owner it keeps the original name and extension the file came in under — the one convenience
past the bytes, so a consumer can show the file and hand it out under its name.

Not here: other metadata of a file (description, role, source identity), its binding to the
consumer's entities, serving it over HTTP, checking its content for safety — those belong to the
consumers and to other layers. The module has no HTTP router and no MCP; consumers call
``services``.

The store list comes from the constructor; the storage root from the core config
(``Config.storage_root``: ``STORAGE_PATH``, by default ``AppPath.storage``) and the temporary
directory from the core paths (``AppPath.tmp``). Two tables, built by the ``csm_*`` migrations on
portable types.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any, ClassVar

from fastapi import FastAPI

from src.core.app_path import AppPath
from src.core.config import Config
from src.core.loggers import get_logger
from src.core.module import Module
from src.core.scheduler.registry import get_registry
from src.modules.core_storage import models  # noqa: F401 — registers the tables in Base.metadata
from src.modules.core_storage.constants import LOG_CHANNEL
from src.modules.core_storage.crud.file import file_stores_in_use
from src.modules.core_storage.layout import StorageLayout, get_layout, set_layout, validate_stores
from src.modules.core_storage.settings import SETTINGS_SCHEMA, set_current
from src.modules.core_storage.tasks.cleanup_task import CleanupTask
from src.modules.core_storage.tasks.reconcile_task import ReconcileTask

_HERE = Path(__file__).resolve().parent
_LOG = get_logger(LOG_CHANNEL)


def root_may_be_shared(config: Config, paths: AppPath) -> bool:
    """A database file outside the profile's folder is most often a copy — a rehearsal of an
    update, a database brought from elsewhere. With the stores left at the profile's own root it
    shares the bytes of the original: its cleanup removes files the original still holds, and its
    reconciliation would take every file the original registered since as bytes without a row."""
    database = config.sqlite_file
    if database is None or config.storage_path:
        return False
    return not database.resolve().is_relative_to(paths.root.resolve())


def layout_of(config: Config, stores: Sequence[str]) -> StorageLayout:
    """The layout this config gives — the root, the temporary folder, the stores — warning when
    the root is likely shared with another base."""
    paths = AppPath.from_root()
    shared = root_may_be_shared(config, paths)
    if shared:
        _LOG.warning(
            "core_storage: the database %s lies outside %s, and STORAGE_PATH is not set — its "
            "files are kept in %s, shared with the database of this profile; give a copy of the "
            "database its own STORAGE_PATH. The reconciliation deletes nothing on this root",
            config.sqlite_file,
            paths.root,
            config.storage_root,
        )
    return StorageLayout(config.storage_root, paths.tmp, stores, root_shared=shared)


class CoreStorageModule(Module):
    name: ClassVar[str] = "core_storage"
    version: ClassVar[str] = "2.5.0"
    description: ClassVar[str] = (
        "File storage: registration, dedup by content, ownership, soft deletion, cleanup and "
        "the reconciliation of the base with the disk."
    )
    migrations_dir = _HERE / "migrations" / "versions"
    settings_schema = SETTINGS_SCHEMA

    def __init__(self, stores: Sequence[str]) -> None:
        self.stores = validate_stores(stores)

    def configure(self, app: FastAPI, config: Config) -> None:
        set_layout(layout_of(config, self.stores))
        for task in (CleanupTask, ReconcileTask):
            if get_registry().get(task.MODULE, task.CODE) is None:
                task.register()

    def on_settings_change(self, store: Any) -> None:
        set_current(store)

    async def on_startup(self, app: FastAPI) -> None:
        get_layout().ensure_dirs()
        orphaned = sorted(set(await file_stores_in_use()) - set(self.stores))
        if orphaned:
            _LOG.warning(
                "core_storage: files of stores off the list stay readable, no new files go there: %s",
                ", ".join(orphaned),
            )


__all__ = ["CoreStorageModule", "layout_of", "root_may_be_shared"]
