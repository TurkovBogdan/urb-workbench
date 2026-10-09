"""The core's two built-in universal guards — the ``allow_all``/``deny_all`` pair.

Real ``auth``/``ability`` (CASL) would come from an auth module via the declarative
``Module.guards``; the core holds only this pair. Function names =
``guard_`` + the kind (``guard_<kind>``) under which the guard sits in the registry.

- ``allow_all`` (``guard_allow_all``) — "allows everything" (lets everyone through). Lifts
  the zone's protection for a specific route via the ``@guard("allow_all")`` mark (login).
- ``deny_all`` (``guard_deny_all``) — "blocks everything" (rejects everyone). Used two ways: as an
  explicit ``@guard("deny_all")`` mark (deliberately switching a route off) and as the zone
  guard's **fallback** when a route has collected neither a zone default nor any marks —
  secure-by-default.
"""

from __future__ import annotations

from starlette.requests import HTTPConnection

from src.core.api.errors import ApiError


async def guard_allow_all(connection: HTTPConnection) -> None:
    return


async def guard_deny_all(connection: HTTPConnection) -> None:
    raise ApiError.unauthorized("Route is closed (no guard)", code="route_closed")


__all__ = ["guard_allow_all", "guard_deny_all"]
