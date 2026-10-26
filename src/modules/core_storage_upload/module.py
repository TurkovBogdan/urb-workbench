"""The ``core_storage_upload`` module — taking files as they are, from a person and from an agent.

A platform module: like every ``core_*`` module it sits under the application levels and imports
only ``src/core`` and ``core_storage``. It takes a file three ways — the body of a request from
the person's page, the body sent for an upload request (both ``/storage/upload``), a path on the
server's disk — and hands it to the holder its code names, through the registry the consumers
fill (``services/holders.py``). On the way it keeps the ceiling (the storage's), the name the
storage could keep, the ``Origin`` of a browser's request or the token of an open request, and
the server's own files out of reach.

Not here: whether a holder takes a file, and its binding row — the consumers'; serving a file —
``core_storage_view``; the words of a refusal for the agent, and the agent's answer to an upload
— the agent surface's (``register_upload_answer``).

One table, ``core_storage_upload_request`` (the ``csu_*`` chain): an upload an agent asked for and
has not sent yet; it outlives a restart and is taken by any server process, and the hourly
cleanup removes the expired ones (``RequestCleanupTask``). Two settings, read at the moment of use
(``settings.py``). The bodies are spooled by the storage itself (``core_storage.file_spool``),
whose cleanup removes one a dead process left. The request's token rides in the address, so
``configure`` keeps it out of the access log (``access_log.py``).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, ClassVar

from fastapi import FastAPI

from src.core.config import Config
from src.core.module import Module
from src.core.scheduler.registry import get_registry
from src.modules.core_storage_upload import models  # noqa: F401 — registers the table in Base.metadata
from src.modules.core_storage_upload.access_log import redact_access_log
from src.modules.core_storage_upload.api import router
from src.modules.core_storage_upload.constants import ROUTER_PREFIX
from src.modules.core_storage_upload.settings import SETTINGS_SCHEMA, set_current
from src.modules.core_storage_upload.tasks.cleanup_task import RequestCleanupTask

_HERE = Path(__file__).resolve().parent


class CoreStorageUploadModule(Module):
    name: ClassVar[str] = "core_storage_upload"
    version: ClassVar[str] = "1.0.0"
    description: ClassVar[str] = (
        "File upload: a person's upload from the interface, an agent's file by a server path "
        "or to an upload address it asked for, handed to the holder the code names."
    )
    migrations_dir = _HERE / "migrations" / "versions"
    storage_router = router
    storage_router_prefix = ROUTER_PREFIX
    settings_schema = SETTINGS_SCHEMA

    def configure(self, app: FastAPI, config: Config) -> None:
        redact_access_log()
        if get_registry().get(RequestCleanupTask.MODULE, RequestCleanupTask.CODE) is None:
            RequestCleanupTask.register()

    def on_settings_change(self, store: Any) -> None:
        set_current(store)


__all__ = ["CoreStorageUploadModule"]
