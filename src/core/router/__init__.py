"""Core routing: zones + the ``guards`` protection subsystem.

A zone = a prefixed space of routers on top of a shared guard registry. The zone
aggregator itself is built FRESH in ``create_app`` (no global singleton —
otherwise repeated ``create_app`` calls in tests would pile up routes). Package contents:
``guards/`` (the protection subsystem: registry + built-in ``allow_all``/``deny_all`` +
the ``@guard`` mark) and the ``internal``/``api``/``webhook`` zones. The active zone is
``internal``; ``api``/``webhook`` come later. The guard surface is re-exported here
from the ``guards`` subpackage as a single entry point.
"""

from __future__ import annotations

from src.core.router.guards import (
    GuardFn,
    GuardRegistry,
    guard,
    guard_allow_all,
    guard_deny_all,
    guard_rules,
    is_allow_all,
    is_deny_all,
    make_zone_guard,
    validate_guard_rules,
)

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
