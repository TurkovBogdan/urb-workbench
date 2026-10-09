"""Route protection subsystem: the guard registry + built-in kinds + the ``@guard`` mark.

A guard is a FastAPI dependency ``async (connection) -> None`` that aborts the request or the
WebSocket handshake by ``raise`` (``ApiError``); its shape is the ``GuardFn`` type. The
implementing function's name =
``guard_`` + kind. Subpackage contents:

- ``registry`` — ``GuardRegistry`` (``kind → GuardFn``) + the ``GuardFn`` type;
- ``universal`` — the core's built-in pair ``guard_allow_all``/``guard_deny_all``;
- ``enforce`` — attaching guards to routes: the ``@guard`` mark + the zone guard
  (the executor) + kind validation at build time.

Real ``auth``/``ability`` (CASL) live in ``core_users`` and flow into the registry from the
declarative ``Module.guards``; the core holds only ``allow_all``/``deny_all``.
"""

from __future__ import annotations

from src.core.router.guards.enforce import (
    guard,
    guard_rules,
    is_allow_all,
    is_deny_all,
    make_zone_guard,
    validate_guard_rules,
)
from src.core.router.guards.registry import GuardFn, GuardRegistry
from src.core.router.guards.universal import guard_allow_all, guard_deny_all

__all__ = [
    "GuardFn",
    "GuardRegistry",
    "guard",
    "guard_allow_all",
    "guard_deny_all",
    "guard_rules",
    "is_allow_all",
    "is_deny_all",
    "make_zone_guard",
    "validate_guard_rules",
]
