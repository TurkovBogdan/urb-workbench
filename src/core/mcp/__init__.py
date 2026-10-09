"""The core's MCP server toolkit — the only import boundary for ``fastmcp``.

The subpackage confines the fork's +13 MB to one backend-only place (only
``mount_mcp_servers`` pulls it in, under ``server_enabled`` — not the worker, not
``build_modules``) and gives modules a single import point:
``from src.core.mcp import make_mcp_server``.

NOT a module: the platform IS the assembler — it owns the ``Module`` contract and mounts
the modules' apps in ``create_app``; a registered module cannot do that.
"""

from __future__ import annotations

from src.core.mcp.auth import McpServerTokenVerifier
from src.core.mcp.audit import McpServerAuditMiddleware
from src.core.mcp.context import (
    McpPrincipal,
    McpServerBuilder,
    McpServerContext,
    TokenResolver,
)
from src.core.mcp.factory import make_mcp_server

__all__ = [
    "McpPrincipal",
    "McpServerAuditMiddleware",
    "McpServerBuilder",
    "McpServerContext",
    "McpServerTokenVerifier",
    "TokenResolver",
    "make_mcp_server",
]
