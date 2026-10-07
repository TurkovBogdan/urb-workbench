"""The ``core_interface`` module — user interface settings in the database.

Answers one question: how the human left the application's appearance — theme, typefaces,
reading area, diagram styling, list layouts. It stores only deviations from the defaults (the
``core_interface_settings`` table); the defaults themselves are declared in ``registry.py``.

Not part of the core, because the core does not consume these values: no server-side line
reads the theme or a typeface — this is data for the browser. Designed for a single user with
no accounts: a setting has no owner, and the key is unique on its own.

No jobs, no guards, no MCP server, no module settings schema: it is a store with a check.
"""

from __future__ import annotations

from pathlib import Path
from typing import ClassVar

from fastapi import FastAPI

from src.core.config import Config
from src.core.loggers import get_logger
from src.core.module import Module
from src.modules.core_interface import models  # noqa: F401 — registers the table in Base.metadata
from src.modules.core_interface import crud
from src.modules.core_interface.api import internal_router
from src.modules.core_interface.constants import LOG_CHANNEL
from src.modules.core_interface.registry import SETTINGS, validate_registry

_HERE = Path(__file__).resolve().parent
_LOG = get_logger(LOG_CHANNEL)


class CoreInterfaceModule(Module):
    name: ClassVar[str] = "core_interface"
    description: ClassVar[str] = (
        "User interface settings: language, theme, typefaces, document and diagram appearance."
    )
    migrations_dir = _HERE / "migrations" / "versions"
    internal_router = internal_router
    internal_router_prefix = "/core/interface"

    def configure(self, app: FastAPI, config: Config) -> None:
        """Registry self-check — here, not in ``on_startup``: building the app fails on an
        exception, while lifespan catches its own and logs them, so a broken map would ship
        silently."""
        validate_registry()

    async def on_startup(self, app: FastAPI) -> None:
        """Clean up keys retired by the previous deploy."""
        removed = await crud.prune_unknown(list(SETTINGS))
        if removed:
            _LOG.info("core_interface: removed settings outside the registry: %d", removed)


__all__ = ["CoreInterfaceModule"]
