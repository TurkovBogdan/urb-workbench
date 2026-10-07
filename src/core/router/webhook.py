"""The ``webhook`` zone — incoming webhooks (a STUB; NOT mounted yet).

The counterpart of ``src/core/router/internal.py`` for the ``/webhook`` zone: receiving webhooks
from external sources. Contents — the modules' sub-routers (``Module.webhook_router``);
protection — a zone guard defaulting to ``WEBHOOK_DEFAULT_GUARDS`` (signature check).

To enable (TODO):
1. Implement and register a guard of kind ``signature`` (validating the source's signature
   over the raw request body) — modelled on the ``internal`` zone guards (``src/core/router/guards/``).
   Mind: the guard needs the RAW body — the zone/ASGI middleware level must not "consume" it.
2. Give modules a ``webhook_router`` / ``webhook_router_prefix`` sub-router (classvar in
   ``src/core/module.py``).
3. Mount it in ``create_app`` behind a flag (like the internal zone):
   ``app.include_router(build_webhook_zone(modules), prefix=WEBHOOK_PREFIX,
   dependencies=[Depends(make_zone_guard(registry, default=WEBHOOK_DEFAULT_GUARDS))])``
   + ``validate_guard_rules(...)``.
"""

from __future__ import annotations

from collections.abc import Sequence

from fastapi import APIRouter

from src.core.module import Module

WEBHOOK_PREFIX = "/webhook"
WEBHOOK_DEFAULT_GUARDS = ["signature"]  # TODO: the "signature" guard kind is not implemented yet


def build_webhook_zone(modules: Sequence[Module]) -> APIRouter:
    """STUB: a fresh webhook-zone aggregator over the modules' ``webhook_router``.

    While ``Module`` has no ``webhook_router``, it is read via ``getattr`` (the zone comes out
    empty). Once the classvar is added it will work like ``build_internal_zone``.
    """
    zone = APIRouter()
    for m in modules:
        router = getattr(m, "webhook_router", None)
        if router is not None:
            zone.include_router(
                router, prefix=getattr(m, "webhook_router_prefix", ""), tags=[m.name]
            )
    return zone


__all__ = ["WEBHOOK_DEFAULT_GUARDS", "WEBHOOK_PREFIX", "build_webhook_zone"]
