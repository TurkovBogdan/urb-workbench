"""Mounting the core HTTP zones onto the FastAPI app.

Extracted from ``app_factory``: building the shared guard registry (``build_guard_registry``)
and mounting the zones under their zone guards with kind validation (``mount_router_zones``).

Responsibility for mount conditions is split:
- ``create_app`` decides whether to mount the HTTP surface AT ALL (the
  ``SERVER_ENABLED`` gate) — visible right in the factory;
- ``mount_router_zones`` decides WHICH zones are mounted and under WHAT conditions —
  each condition is spelled out here explicitly (internal — always; mcp — separate
  ASGI sub-apps via ``mount_mcp_servers``; api/webhook — off for now).

``_attach_zone`` is the bare mechanics of mounting one zone, with no conditions.
"""

from __future__ import annotations

from collections.abc import Sequence
from contextlib import AbstractAsyncContextManager
from typing import Any

from fastapi import APIRouter, Depends, FastAPI

from src.core.config import Config
from src.core.loggers import get_logger
from src.core.module import Module
from src.core.router import (
    GuardRegistry,
    guard_allow_all,
    guard_deny_all,
    make_zone_guard,
    validate_guard_rules,
)
from src.core.router.internal import (
    INTERNAL_DEFAULT_GUARDS,
    INTERNAL_PREFIX,
    build_internal_zone,
    make_request_delay,
)
from src.core.router.mcp import mount_mcp_servers
from src.core.router.spa import mount_spa
from src.core.router.storage import (
    STORAGE_DEFAULT_GUARDS,
    STORAGE_PREFIX,
    build_storage_zone,
)

_LOG = get_logger()


def build_guard_registry(modules: Sequence[Module]) -> GuardRegistry:
    """Build the shared guard registry: the core built-ins + the modules' kinds.

    The core holds only ``allow_all``/``deny_all``; real ``auth``/``ability`` would come from an
    auth module via the declarative ``Module.guards``. Without one, the internal zone defaults
    to the built-in ``allow_all`` (see ``INTERNAL_DEFAULT_GUARDS``).
    """
    registry = GuardRegistry()
    registry.add("allow_all", guard_allow_all)
    registry.add("deny_all", guard_deny_all)
    for m in modules:
        for kind, fn in m.guards.items():
            registry.add(kind, fn)
    return registry


def _attach_zone(
    app: FastAPI,
    registry: GuardRegistry,
    zone: APIRouter,
    prefix: str,
    default_guards: list[str],
    *,
    extra_deps: Sequence[Any] = (),
) -> None:
    """The mechanics of mounting ONE zone (no conditions — ``mount_router_zones`` decides those):
    zone guard (+ optional ``extra_deps``) → ``include_router`` under the prefix →
    validation that every referenced kind is registered."""
    deps = [Depends(make_zone_guard(registry, default=default_guards)), *extra_deps]
    app.include_router(zone, prefix=prefix, dependencies=deps)
    validate_guard_rules(app, registry, defaults=default_guards)


def mount_router_zones(
    app: FastAPI, modules: Sequence[Module], config: Config
) -> list[AbstractAsyncContextManager[None]]:
    """Mount the HTTP zones onto ``app``. The mount condition of EVERY zone lives here, explicitly.

    Called from ``create_app`` under the ``SERVER_ENABLED`` gate (the gate itself is visible in
    the factory). Returns the lifespan CMs of the mounted MCP servers — ``create_app`` composes
    them into its own lifespan (otherwise the fork's session manager never starts).
    """
    registry = build_guard_registry(modules)

    # internal — mounted ALWAYS (core + SPA). DEBUG: the artificial delay runs
    # AFTER the guard (rejected requests don't wait), added only when ms > 0.
    internal_extra: list[Any] = []
    if config.server_debug_delay_ms > 0:
        internal_extra.append(Depends(make_request_delay(config.server_debug_delay_ms)))
        _LOG.warning(
            "mount_router_zones: SERVER_DEBUG_DELAY_MS=%d — internal API artificially "
            "slowed by %d ms/request (DEBUG; keep 0 in prod)",
            config.server_debug_delay_ms,
            config.server_debug_delay_ms,
        )
    _attach_zone(
        app,
        registry,
        build_internal_zone(modules),
        INTERNAL_PREFIX,
        INTERNAL_DEFAULT_GUARDS,
        extra_deps=internal_extra,
    )

    # storage — serving files from the root /storage (guard auth). Only protected goes
    # through here; public is served by nginx directly, private is closed. Always mounted.
    _attach_zone(
        app,
        registry,
        build_storage_zone(modules),
        STORAGE_PREFIX,
        STORAGE_DEFAULT_GUARDS,
    )

    # spa — the built frontend from web/dist is served by the same HTTP server. It is a middleware
    # (outside zones/guards): it short-circuits any GET outside the API prefixes before routing,
    # so the mount order does not matter. No build → no-op (see mount_spa).
    mount_spa(app)

    # mcp — each module's MCP server is mounted as a separate ASGI sub-app
    # (the fastmcp fork, Streamable HTTP) under /mcp/<code>; auth lives inside the server
    # (McpServerTokenVerifier), NOT in a zone guard (mount bypasses dependencies).
    # The returned lifespans are started in create_app.
    mcp_lifespans = mount_mcp_servers(app, modules, config)

    # api / webhook — stubs, NOT mounted yet (the scope/signature guard kinds are not
    # implemented yet; see router/api.py, router/webhook.py).
    return mcp_lifespans


__all__ = ["build_guard_registry", "mount_router_zones"]
