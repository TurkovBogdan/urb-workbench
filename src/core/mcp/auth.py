"""Bearer verifier for MCP servers — agnostic, does not import the auth module.

A mounted ASGI sub-app bypasses FastAPI ``dependencies=[...]``, so auth lives INSIDE the
server through the fork's ``TokenVerifier.verify_token`` — the only point that survives
the mount boundary.

The ``(token, scope) -> principal | None`` resolver is INJECTED (the auth module supplies
it via ``Module.mcp_token_resolver``), just as guards flow in through ``Module.guards``:
the core never imports a module. This file is backend-only (only ``mount_mcp_servers``
pulls it in, under ``server_enabled``).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastmcp.server.auth import AccessToken, TokenVerifier

if TYPE_CHECKING:
    from src.core.mcp.context import TokenResolver

# The token's auth scope (defined by the auth module). Distinct from the router *zone*
# ``/mcp``: a token of another scope presented here is a free reject.
_MCP_SCOPE = "mcp"


class McpServerTokenVerifier(TokenVerifier):
    """Resolves a bearer token into an MCP ``AccessToken`` through the injected resolver.

    ``verify_token`` calls ``resolve(token, "mcp")`` (checking the token is of type
    ``mcp``) and maps the principal to ``AccessToken(client_id=str(id), scopes=[group])``;
    a ``None`` from the verifier → 401 before any tool runs.
    """

    def __init__(self, resolve: "TokenResolver") -> None:
        super().__init__()
        self._resolve = resolve

    async def verify_token(self, token: str) -> AccessToken | None:
        principal = await self._resolve(token, _MCP_SCOPE)
        if principal is None:
            return None
        return AccessToken(
            token=token,
            client_id=str(principal.id),
            scopes=[principal.group],
        )


__all__ = ["McpServerTokenVerifier"]
