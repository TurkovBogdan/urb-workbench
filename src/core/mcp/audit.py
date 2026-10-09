"""Server-side MCP audit middleware: writes every tool call to ``mcp/audit``.

The fork's ``Middleware.on_call_tool`` wraps every tool of every mounted server (one
instance per ``McpServerContext``). Log line:
``principal · tool · argument-summary · ok/err · ms``. The principal is read from the
auth context (``get_access_token().client_id`` = ``user.id``); with an in-memory
``Client`` (tests, no transport/auth) there is no token → ``-``.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

from fastmcp.server.dependencies import get_access_token
from fastmcp.server.middleware import Middleware

from src.core.loggers import get_logger

if TYPE_CHECKING:
    from fastmcp.server.middleware import CallNext, MiddlewareContext
    from fastmcp.tools.tool import ToolResult

_LOG = get_logger("mcp/audit")
_ARGS_MAX = 200  # truncate the argument summary so the log does not bloat


def _summarize(arguments: Any) -> str:
    s = repr(arguments)
    return s if len(s) <= _ARGS_MAX else s[:_ARGS_MAX] + "…"


class McpServerAuditMiddleware(Middleware):
    """Logs the outcome of every ``call_tool`` to the ``mcp/audit`` channel."""

    async def on_call_tool(
        self,
        context: "MiddlewareContext",
        call_next: "CallNext",
    ) -> "ToolResult":
        token = get_access_token()
        principal = token.client_id if token is not None else "-"
        name = context.message.name
        args = _summarize(context.message.arguments)
        start = time.monotonic()
        try:
            result = await call_next(context)
        except Exception as exc:  # noqa: BLE001 — re-raised after logging
            ms = (time.monotonic() - start) * 1000
            _LOG.info(
                "mcp user=%s tool=%s args=%s err=%r %.0fms",
                principal, name, args, exc, ms,
            )
            raise
        ms = (time.monotonic() - start) * 1000
        _LOG.info(
            "mcp user=%s tool=%s args=%s ok %.0fms", principal, name, args, ms
        )
        return result


__all__ = ["McpServerAuditMiddleware"]
