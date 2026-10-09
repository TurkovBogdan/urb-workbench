"""The ``api`` zone — the external token API (a STUB; NOT mounted yet).

The counterpart of ``src/core/router/internal.py`` for the ``/api`` zone: third-party
integrations by bearer token + scope. Contents — the modules' sub-routers (``Module.api_router``);
protection — a zone guard defaulting to ``API_DEFAULT_GUARDS``.

To enable (TODO):
1. Implement and register a guard of kind ``scope`` (``Security`` + OAuth2 scopes) —
   the same way it is done for the ``internal`` zone (``src/core/router/guards/``).
2. Give modules an ``api_router`` / ``api_router_prefix`` sub-router (like ``internal_router``;
   add the classvar to ``src/core/module.py``).
3. Mount it in ``create_app`` behind a flag (like the internal zone):
   ``app.include_router(build_api_zone(modules), prefix=API_PREFIX,
   dependencies=[Depends(make_zone_guard(registry, default=API_DEFAULT_GUARDS))])``
   + ``validate_guard_rules(...)``.
"""

from __future__ import annotations

from collections.abc import Sequence

from fastapi import APIRouter

from src.core.module import Module

API_PREFIX = "/api"
API_DEFAULT_GUARDS = ["scope"]  # TODO: the "scope" guard kind is not implemented/registered yet


def build_api_zone(modules: Sequence[Module]) -> APIRouter:
    """STUB: a fresh api-zone aggregator over the modules' ``api_router``.

    While ``Module`` has no ``api_router``, it is read via ``getattr`` (the zone comes out
    empty). Once the classvar is added it will work like ``build_internal_zone``.
    """
    zone = APIRouter()
    for m in modules:
        router = getattr(m, "api_router", None)
        if router is not None:
            zone.include_router(
                router, prefix=getattr(m, "api_router_prefix", ""), tags=[m.name]
            )
    return zone


__all__ = ["API_DEFAULT_GUARDS", "API_PREFIX", "build_api_zone"]
