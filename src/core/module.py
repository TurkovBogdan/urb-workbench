"""The module contract: what a module provides to the core.

Module is a provider class with explicit lifecycle hooks. It replaces the
``ModuleSpec`` dataclass + a single ``register`` callable: each phase gets a named
method the core calls at the right moment.

Phases:
- ``configure(app, config)`` — sync, build phase in ``create_app``. Registers
  routers, scheduler tasks, sync resources with safe defaults. No DB yet.
- ``on_settings_change(store)`` — sync, runtime phase. Fires on the initial
  store install (lifespan startup) and on every PUT/reset through the API.
- ``on_startup(app)`` — async, after all modules + DB + migrations + settings.
  The place for async initialisation: seeding data, registering agents, etc.
- ``shutdown(app)`` — async, lifespan finally (in reverse order).

Every hook has an empty default on the base class — modules override what they
need. ``name`` is the only required attribute.
"""

from __future__ import annotations

from abc import ABC
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar

from fastapi import APIRouter, FastAPI
from pydantic_settings import BaseSettings

if TYPE_CHECKING:
    from src.core.settings.schema import ModuleSchema
    from src.core.config import Config
    from src.core.mcp import McpServerBuilder, TokenResolver
    from src.core.module_state import ModuleStore
    from src.core.router import GuardFn


class Module(ABC):
    """Base class of an application module."""

    # ── declarative attributes (class-level) ─────────────────────────────
    name: ClassVar[str]
    # Human-readable description of the module's purpose (prose). Exposed via the settings
    # API ``/modules`` for the card on ``/core/settings``; ``name`` stays the technical code.
    description: ClassVar[str] = ""
    migrations_dir: ClassVar[Path | None] = None
    config_cls: ClassVar[type[BaseSettings] | None] = None
    settings_schema: ClassVar["ModuleSchema | None"] = None
    # The module's guards (``kind → guard``); the core merges them into the shared registry
    # before mounting the zones (``_build_guard_registry``). The registry is shared — a kind
    # works in any zone. Empty for most; an auth module would supply ``auth``/``ability``.
    # Declared BEFORE the routers: guards are the protection, routers the protected surface
    # (registry first, then routes — the same order as the mounting in create_app).
    guards: ClassVar[dict[str, "GuardFn"]] = {}
    # Sub-router of the internal zone. create_app includes it in the zone aggregator
    # (instead of app.include_router("/internal/<m>") in configure). None — a module without HTTP.
    # internal_router_prefix — the sub-prefix inside the internal zone (e.g. "/my-module"); it is
    # not derived from name (kebab vs underscore), hence set explicitly. The name is qualified
    # by the zone — future api/webhook get their own (api_router/_prefix, webhook_router/_prefix).
    internal_router: ClassVar[APIRouter | None] = None
    internal_router_prefix: ClassVar[str] = ""
    # Sub-router of the storage zone (serving files from the ``/storage`` root). Mirrors
    # internal_router: the core includes it in the zone aggregator. None — a module with no
    # file surface (a storage module would supply one).
    storage_router: ClassVar[APIRouter | None] = None
    storage_router_prefix: ClassVar[str] = ""
    # The module's MCP servers: ``code -> mcp_server`` (a ``(ctx) -> FastMCP`` constructor).
    # Declarative, mirroring ``guards``: the ``code`` key = the ``/mcp/<code>`` URL segment,
    # the value is a FUNCTION (not an instance), so declaring the dict does NOT import
    # ``fastmcp`` (the worker stays clean). A module may supply several servers; empty = non-MCP.
    # Mounting + auth + audit come from the core (``mount_mcp_servers``, backend-only).
    mcp_servers: ClassVar[dict[str, "McpServerBuilder"]] = {}
    # MCP token resolver ``(token, scope) -> principal | None`` (mirrors ``guards`` — a
    # declarative seam through which the core gets the resolver WITHOUT importing the module).
    # Supplied by an auth module (= its ``resolve_token``); ``mount_mcp_servers`` assembles
    # it into the single ``McpServerTokenVerifier``. None — the module supplies no
    # resolver.
    mcp_token_resolver: ClassVar["TokenResolver | None"] = None

    # ── state store ──────────────────────────────────────────────────────
    @property
    def store(self) -> "ModuleStore":
        """Arbitrary runtime state of the module (``core_modules_state``).

        The store code is ``self.name``, so the module does not repeat its own code:
        ``await self.store.set("import_cursor", {...})``. For internal data
        (cursors, counters, markers), not for user configuration (that lives in the
        settings store). Available once the DB is initialised (startup/runtime).
        """
        from src.core.module_state import module_store

        return module_store(self.name)

    # ── build phase ──────────────────────────────────────────────────────
    def configure(self, app: FastAPI, config: "Config") -> None:
        """Sync. Registers routers, scheduler tasks, sync resources.

        Resources created here MUST be usable in a safe no-op state until the
        first ``on_settings_change(store)`` in lifespan startup.
        There is no DB yet, and no settings store either.
        """

    # ── settings event ───────────────────────────────────────────────────
    def on_settings_change(self, store: Any) -> None:
        """Sync. The initial store install (lifespan startup) and every PUT/reset.

        Async I/O is forbidden. If an async reaction is needed — ``asyncio.create_task``
        inside the hook, or a flag the next scheduler tick picks up.
        """

    # ── startup phase (async, all modules ready) ──────────────────────────
    async def on_startup(self, app: FastAPI) -> None:
        """Async. All modules are configured, the DB is ready, settings are loaded.

        Called once in the lifespan, before scheduler.start().
        Suited to seeding data, registering agents and other async initialisation.
        """

    # ── shutdown phase ──────────────────────────────────────────────────
    async def shutdown(self, app: FastAPI) -> None:
        """Before ``scheduler.stop()`` / ``close_database()``.

        Reverse order of the module list. Async teardown of resources
        (httpx clients, pools, etc.).
        """


__all__ = ["Module"]
