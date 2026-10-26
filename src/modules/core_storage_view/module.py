"""The ``core_storage_view`` module — serving stored files over HTTP.

A platform module, the HTTP face of ``core_storage`` for reading: like every ``core_*`` module it
sits under the application levels and imports only ``src/core`` and ``core_storage``. It serves
the files of the ``public`` store by code in the core zone ``/storage`` — to open in a tab and to
save under the name the address gives (``/download/<name>``), with the headers that keep an
uploaded document from acting with the app's rights.

Not here: taking a file in — a person's upload, an agent's file by a path or at an upload address —
that is ``core_storage_upload``; a file's binding to an entity; any MCP surface. ``core_storage``
itself keeps no routes. No tables, no migrations, no settings.
"""

from __future__ import annotations

from typing import ClassVar

from src.core.module import Module
from src.modules.core_storage_view.api import router
from src.modules.core_storage_view.constants import ROUTER_PREFIX


class CoreStorageViewModule(Module):
    name: ClassVar[str] = "core_storage_view"
    version: ClassVar[str] = "2.1.0"
    description: ClassVar[str] = "Serving stored files: opening and downloading public files by code."
    storage_router = router
    storage_router_prefix = ROUTER_PREFIX


__all__ = ["CoreStorageViewModule"]
