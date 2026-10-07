"""The origin of an edit: which interface tab made it.

A tab sends its random id in the ``X-Client-Id`` header of every request. The middleware puts it
into a context variable for the duration of the request; the change collector reads it on flush
and puts it into the feed message as ``origin``. That lets a tab recognise the echo of its own
saves and not re-read what it has just written itself.

Without the header — the MCP agent, background jobs, other clients — ``origin`` is empty, i.e.
"not you" for every tab.

The middleware is plain ASGI, not ``BaseHTTPMiddleware``: the variable is set in the same task
that runs the request handler, so it is reliably visible from SQLAlchemy session event handlers.
"""

from __future__ import annotations

from contextvars import ContextVar

CLIENT_ID_HEADER = "x-client-id"

# A length cap: the header comes from outside, and an unbounded string would ride along in every
# feed message to every tab.
_MAX_LEN = 64

current_origin: ContextVar[str | None] = ContextVar("core_changes_origin", default=None)


class OriginMiddleware:
    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        origin = None
        for name, value in scope.get("headers", ()):
            if name == CLIENT_ID_HEADER.encode():
                origin = value.decode("latin-1")[:_MAX_LEN] or None
                break
        token = current_origin.set(origin)
        try:
            await self.app(scope, receive, send)
        finally:
            current_origin.reset(token)


__all__ = ["CLIENT_ID_HEADER", "OriginMiddleware", "current_origin"]
