"""MCP server context: the shared wiring handed to every module's builder.

``McpServerContext`` is built ONCE in ``mount_mcp_servers`` and passed to every module's
``mcp_server(ctx)``. It carries the agnostic verifier (shared by all servers), the audit
middleware and the ``allowed_hosts`` list (DNS-rebinding protection is attached by the
ASGI layer through ``TrustedHostMiddleware`` at ``http_app()`` time — the ``fastmcp`` 3.x
fork lacks the bundled SDK's ``TransportSecuritySettings``).

The ``TokenResolver`` / ``McpServerBuilder`` types are declared here (a leaf module with
no top-level ``fastmcp`` import) so that ``core/module.py`` can type
``Module.mcp_servers`` / ``Module.mcp_token_resolver`` without dragging in +13 MB.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from fastmcp import FastMCP
    from fastmcp.server.auth import TokenVerifier
    from fastmcp.server.middleware import Middleware


class McpPrincipal(Protocol):
    """Duck type of the principal returned by the token resolver.

    Matches the auth module's principal on the fields in use — the core does NOT import
    it, and reads only ``id``/``group``.
    """

    id: int
    group: str


# Token resolver: (token, scope) -> principal | None. Supplied by the auth module
# via ``Module.mcp_token_resolver``.
TokenResolver = Callable[[str, str], Awaitable["McpPrincipal | None"]]

# MCP server builder: ``(ctx) -> FastMCP``. In a module it is ALWAYS named
# ``mcp_server`` and placed in ``Module.mcp_servers`` under its ``code`` key.
McpServerBuilder = Callable[["McpServerContext"], "FastMCP"]


@dataclass(frozen=True)
class McpServerContext:
    """Shared wiring passed to the builder of every MCP server."""

    auth: "TokenVerifier"
    audit: "Middleware"
    allowed_hosts: list[str] = field(default_factory=list)


__all__ = [
    "McpPrincipal",
    "McpServerBuilder",
    "McpServerContext",
    "TokenResolver",
]
