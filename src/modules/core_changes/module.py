"""The ``core_changes`` module — the data changes feed for live frontend updates.

**Level 0**, infrastructure: it sits in the list before the modules whose entities it carries.
They declare them in their own ``configure()`` (``register_entity``), and the session
subscription is installed here, in this module's ``configure()`` — before the first request and
the first write.

The module knows no concrete entity: what goes into the stream is decided by the data owner (see
``entities.py``). No tables of its own — the stream lives in process memory (``bus.py``).
"""

from __future__ import annotations

from typing import ClassVar

from fastapi import FastAPI

from src.core.config import Config
from src.core.module import Module
from src.modules.core_changes.api import router
from src.modules.core_changes.capture import install
from src.modules.core_changes.origin import OriginMiddleware


class CoreChangesModule(Module):
    name: ClassVar[str] = "core_changes"
    description: ClassVar[str] = (
        "Changes feed: tells the interface which declared entities were created, updated or "
        "deleted, so open screens refresh themselves."
    )
    internal_router = router
    internal_router_prefix = "/core/changes"

    def configure(self, app: FastAPI, config: Config) -> None:
        install()
        # The originating tab's mark (``X-Client-Id``) for every request — see ``origin.py``.
        app.add_middleware(OriginMiddleware)


__all__ = ["CoreChangesModule"]
