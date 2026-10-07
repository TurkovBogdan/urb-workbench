"""The shared guard registry: ``kind → guard``. NOT split by zone.

``GuardFn`` is the shape of a guard callable: a FastAPI dependency
``async (connection) -> None`` that aborts the request by ``raise`` (``ApiError``).
The registry is built once while ``create_app`` assembles the app (the core pre-registers
``allow_all``/``deny_all``, modules add their own via the declarative
``Module.guards``) and is never mutated afterwards. ``@guard("kind")`` refers to a guard by
name; a registered guard works in any zone.

The argument is an ``HTTPConnection``, not a ``Request``: a zone holds WebSocket routes too
(the change feed), and FastAPI hands a ``Request`` parameter nothing on a WebSocket route — the
guard would fail with a ``TypeError`` instead of deciding. Raised before ``accept``, an
``ApiError`` becomes a refused handshake.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from starlette.requests import HTTPConnection

GuardFn = Callable[[HTTPConnection], Awaitable[None]]


class GuardRegistry:
    """A flat ``kind → GuardFn`` registry (not bound to any zone)."""

    def __init__(self) -> None:
        self._guards: dict[str, GuardFn] = {}

    def add(self, kind: str, fn: GuardFn) -> None:
        """Register a guard under a kind. Registering it twice is an error."""
        if kind in self._guards:
            raise ValueError(f"guard '{kind}' is already registered")
        self._guards[kind] = fn

    def has(self, kind: str) -> bool:
        return kind in self._guards

    def resolve(self, kind: str) -> GuardFn:
        return self._guards[kind]


__all__ = ["GuardFn", "GuardRegistry"]
