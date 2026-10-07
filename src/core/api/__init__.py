"""Standard building blocks for the core HTTP API: errors and handlers.

Public surface for modules:
- ``ApiError`` / ``ErrorBody`` — the single error format and its constructors;
- ``Paged`` — a paginated list envelope for read endpoints;
- ``register_exception_handlers`` — attach the handlers in ``create_app``.

The core does NOT know about users: the principal and the ``current_user`` dependency live in
the auth module (the auth provider, if one is added); the core only provides the
``request.state`` channel and ``ApiError``.
"""

from __future__ import annotations

from src.core.api.errors import ApiError, ErrorBody
from src.core.api.exceptions import register_exception_handlers
from src.core.api.pagination import Paged

__all__ = [
    "ApiError",
    "ErrorBody",
    "Paged",
    "register_exception_handlers",
]
