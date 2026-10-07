"""The ``storage`` zone — serving files from the root (mounted at ``/storage``).

The counterpart of ``src/core/router/internal.py``, but the prefix is a root-level ``/storage``
(not ``/internal/...``): the client reaches a file by a "clean" URL, usable in
``<img src>`` and direct links. Contents — the modules' sub-routers (``Module.storage_router``);
protection — a zone guard defaulting to ``STORAGE_DEFAULT_GUARDS`` (``auth`` — the project session).

Only ``protected`` goes through the backend (permission check → an X-Accel-Redirect response,
nginx streams the bytes itself). ``public`` is served by nginx straight from disk and never
reaches the backend; ``private`` is closed to the outside (nginx ``deny all``).

The zone is built FRESH on every ``create_app`` (like internal) — no singleton.
"""

from __future__ import annotations

from collections.abc import Sequence

from fastapi import APIRouter

from src.core.module import Module

STORAGE_PREFIX = "/storage"
# The bare core has no auth module, so the default is the built-in ``allow_all`` (see INTERNAL_DEFAULT_GUARDS).
STORAGE_DEFAULT_GUARDS = ["allow_all"]


def build_storage_zone(modules: Sequence[Module]) -> APIRouter:
    """A fresh storage-zone aggregator over the modules' ``storage_router``."""
    zone = APIRouter()
    for m in modules:
        if m.storage_router is not None:
            zone.include_router(
                m.storage_router, prefix=m.storage_router_prefix, tags=[m.name]
            )
    return zone


__all__ = ["STORAGE_DEFAULT_GUARDS", "STORAGE_PREFIX", "build_storage_zone"]
