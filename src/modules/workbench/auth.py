"""The MCP token resolver — a stopgap until an auth module appears.

``mount_mcp_servers`` collects **exactly one** ``mcp_token_resolver`` from the modules and builds
from it a shared verifier for all mounted servers. A provider must exist, and there must be only
one: with none, mounting refuses; with two, likewise.

**Why it lives here.** The token is checked only on the way into an MCP server, and every MCP
server of the application is this module's — the gate belongs with what it guards. Before the
agent surface moved here the resolver sat on ``workspace``, chosen for being at level 1 and
outliving everything above it; that reason was about not losing MCP with a deleted module, and
it holds here too: without ``workbench`` there is no MCP server left to guard.

The check is simple: the presented bearer is compared with the static token from ENV
(``Config.mcp_token``). Empty = local mode with no check (allow-all, dev). A future auth module
will take over this role along with issuing tokens, and the declaration will move there then.

Pulls in no ``fastmcp``: only ``Config`` and a dataclass. The principal type is duck-typed
(``id``/``group``), as ``McpServerTokenVerifier`` expects.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from src.core.config import Config

if TYPE_CHECKING:
    from src.core.mcp.context import McpPrincipal

_MCP_SCOPE = "mcp"


@dataclass(frozen=True)
class _StaticPrincipal:
    id: int = 0
    group: str = "workspace"


async def resolve_mcp_token(token: str, scope: str) -> "McpPrincipal | None":
    """Bearer → principal; a foreign scope or a mismatched token — ``None`` (verifier gives 401)."""
    if scope != _MCP_SCOPE:
        return None
    configured = Config().mcp_token
    if not configured:
        return _StaticPrincipal()
    return _StaticPrincipal() if token == configured else None


__all__ = ["resolve_mcp_token"]
