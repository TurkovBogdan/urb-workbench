"""The ``internal`` zone — assembly of the aggregating router (mounted at ``/internal``).

Zone contents: the public ``/health`` + core endpoints (``/core/settings``) +
the modules' sub-routers (``Module.internal_router``/``internal_router_prefix``).

The zone is built FRESH on every ``create_app`` (``build_internal_zone`` returns a
new ``APIRouter``) — no global singleton, otherwise repeated ``create_app`` calls in
tests would pile up routes. Protection is attached by ``mount_router_zones`` (``router/mounting.py``)
as a zone guard (``make_zone_guard(registry, default=INTERNAL_DEFAULT_GUARDS)``); this file holds
only the contents.

``api``/``webhook`` are separate stub zones alongside (``api.py``/``webhook.py``), not mounted yet.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Sequence

from fastapi import APIRouter, Request

from src.core.settings.api import router as settings_router
from src.core.update.api import router as update_router
from src.core.module import Module
from src.core.router.degraded import health_payload
from src.core.router.guards import guard

# The zone's mount prefix and its default guard kinds (default-on).
# The bare core has no auth module, so the default is the built-in ``allow_all``.
# Once an auth provider arrives (its own ``Module.guards`` with an ``auth`` kind), put ``["auth"]`` back here.
INTERNAL_PREFIX = "/internal"
INTERNAL_DEFAULT_GUARDS = ["allow_all"]

HEALTH_ROUTE = "/health"
# The full path is needed outside: the behind-chain gate exempts exactly it (router/degraded.py).
HEALTH_PATH = INTERNAL_PREFIX + HEALTH_ROUTE

APP_ROUTE = "/core/app"


def make_request_delay(ms: int) -> Callable[[], Awaitable[None]]:
    """DEBUG-only zone dependency: delays every request in the zone by ``ms`` milliseconds.

    For debugging the frontend (skeletons/loaders). Mounted only when ``ms > 0`` (see
    ``mount_router_zones`` in ``router/mounting.py``) — zero overhead in prod.
    Attached AFTER the guard, so rejected (401) requests don't wait for nothing.
    """
    seconds = ms / 1000

    async def _delay() -> None:
        await asyncio.sleep(seconds)

    return _delay


@guard("allow_all")
async def _health(request: Request) -> dict[str, object]:
    """Public liveness of the internal zone (no auth). Reachable only while the
    zone is mounted ⇒ reflects that the API is actually up (SERVER_ENABLED).

    A migration chain that is behind answers 200 and ``degraded`` — the MCP shim would take a
    non-200 as the backend's death and go spawn a second one (see ``router/degraded.py``)."""
    return health_payload(request.app)


async def _app_flags(request: Request) -> dict[str, object]:
    """The process-level switches the SPA shapes itself by. The values are those this process
    started with, not the current ``.env``: an edit there takes effect only after a restart."""
    return {"dev_mode": request.app.state.config.app_dev_mode}


def build_internal_zone(modules: Sequence[Module]) -> APIRouter:
    """A fresh internal-zone aggregator: health + core + the modules' sub-routers."""
    zone = APIRouter()
    zone.add_api_route(HEALTH_ROUTE, _health, methods=["GET"], tags=["core"])
    zone.add_api_route(APP_ROUTE, _app_flags, methods=["GET"], tags=["core"])
    zone.include_router(settings_router, prefix="/core/settings", tags=["core"])
    zone.include_router(update_router, prefix="/core/update", tags=["core"])
    for m in modules:
        if m.internal_router is not None:
            zone.include_router(
                m.internal_router, prefix=m.internal_router_prefix, tags=[m.name]
            )
    return zone


__all__ = [
    "APP_ROUTE",
    "HEALTH_PATH",
    "HEALTH_ROUTE",
    "INTERNAL_DEFAULT_GUARDS",
    "INTERNAL_PREFIX",
    "build_internal_zone",
    "make_request_delay",
]
