"""Core test helpers.

``auth``/``ability`` are no longer core mocks — ``core_users`` provides them. So that core
tests can mount the internal zone (default ``["auth"]``) without bringing up all of
``core_users`` with its DB, we slip in a light stub module: ``auth`` sets a fake admin,
``ability`` lets everything through.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import ClassVar

from starlette.requests import HTTPConnection

from src.core.module import Module

# The core knows nothing about the principal (duck-typed request.state.user); the model
# lives in core_users. Core tests only need an object of the right shape.
_STUB_USER = SimpleNamespace(
    id=1, email="admin@example.local", name="admin", group="admin", is_active=True
)


async def _stub_auth(connection: HTTPConnection) -> None:
    connection.state.user = _STUB_USER


async def _stub_ability(connection: HTTPConnection) -> None:
    return


class AuthStubModule(Module):
    """Passthrough ``auth``/``ability`` for internal-zone tests (declarative)."""

    name: ClassVar[str] = "auth_stub"
    guards = {"auth": _stub_auth, "ability": _stub_ability}


__all__ = ["AuthStubModule"]
