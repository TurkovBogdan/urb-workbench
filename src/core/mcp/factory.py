"""Building one ``FastMCP`` server under a ``McpServerContext``.

``make_mcp_server`` is the only factory that constructs a ``FastMCP``: a module's
``mcp_server(ctx)`` calls it, then registers its own tools (``register(mcp)``). Every
server gets the shared ``auth`` (bearer) + ``audit`` (per-tool log) for free.
``transport``/``allowed_hosts`` are attached later, on ``http_app()`` in
``mount_mcp_servers`` (the ASGI layer).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastmcp import FastMCP

from src.core.version import app_version

if TYPE_CHECKING:
    from src.core.mcp.context import McpServerContext


def make_mcp_server(
    code: str, instructions: str, ctx: "McpServerContext"
) -> FastMCP:
    """A ``FastMCP`` named ``code``, with the shared auth + audit from ``ctx``.

    ``name=code`` matches the ``/mcp/<code>`` URL segment; the 3.x fork accepts ``version``
    directly (the bundled SDK's ``_mcp_server.version`` workaround is not needed), and it is
    taken from the installation manifest — the MCP surface has no version number of its own.
    """
    return FastMCP(
        name=code,
        instructions=instructions,
        version=app_version(),
        auth=ctx.auth,
        middleware=[ctx.audit],
    )


__all__ = ["make_mcp_server"]
