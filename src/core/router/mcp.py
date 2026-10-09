"""The ``mcp`` zone — modules as MCP servers under ``/mcp/<code>``.

Not an APIRouter zone: each MCP server is a separate ASGI sub-app (the ``fastmcp``
fork, Streamable HTTP) mounted via ``app.mount``. The mount boundary bypasses
FastAPI ``dependencies=[...]``, so auth lives INSIDE the server
(``McpServerTokenVerifier``) rather than in a zone guard.

``mount_mcp_servers`` is the zone glue: it builds one ``McpServerContext`` (shared
verifier + audit + allowed_hosts), mounts every module's ``(code, mcp_server)``
and returns their lifespans up to ``create_app`` (they are composed there —
without that the fork's session manager is never initialised → 500).

The ``src.core.mcp`` import (→ ``fastmcp``, +13 MB) is kept INSIDE the function: this module
is pulled in by ``app_factory`` → ``mounting`` in every process, while the mount itself runs only
under ``server_enabled`` — that way the fork never lands in the worker.
"""

from __future__ import annotations

from collections.abc import Sequence
from contextlib import AbstractAsyncContextManager
from typing import TYPE_CHECKING

from src.core.config import Config
from src.core.loggers import get_logger
from src.core.module import Module

if TYPE_CHECKING:
    from src.core.mcp import TokenResolver

_LOG = get_logger()

# The zone's mount prefix: ``/mcp/<code>`` per server.
MCP_PREFIX = "/mcp"


def _collect_resolver(modules: Sequence[Module]) -> "TokenResolver":
    """The single ``mcp_token_resolver`` across the modules (like ``build_guard_registry``).

    The auth module supplies it; several suppliers → a configuration error.
    Called only when there is at least one MCP server (otherwise the zone is empty).
    """
    resolvers = [m.mcp_token_resolver for m in modules if m.mcp_token_resolver is not None]
    if not resolvers:
        raise RuntimeError(
            "mount_mcp_servers: no module supplied an mcp_token_resolver "
            "(an auth module was expected) — the MCP servers would be left without auth"
        )
    if len(resolvers) > 1:
        raise RuntimeError(
            f"mount_mcp_servers: several mcp_token_resolver ({len(resolvers)}) — "
            "exactly one was expected (the auth module)"
        )
    return resolvers[0]


def mount_mcp_servers(
    app, modules: Sequence[Module], config: Config
) -> list[AbstractAsyncContextManager[None]]:
    """Mount every module's MCP servers under ``/mcp/<code>``.

    Returns each sub-app's lifespan CM — ``create_app`` enters them
    via ``AsyncExitStack`` (initialising the fork's session manager). A duplicate ``code``
    across modules → ``RuntimeError`` (a loud refusal, not a silent overwrite).
    """
    # The fastmcp code is imported here, not at the top level (the backend-only boundary).
    from starlette.middleware import Middleware as ASGIMiddleware
    from starlette.middleware.trustedhost import TrustedHostMiddleware

    from src.core.mcp import (
        McpServerAuditMiddleware,
        McpServerContext,
        McpServerTokenVerifier,
    )

    pairs = [
        (code, builder)
        for m in modules
        for code, builder in m.mcp_servers.items()
    ]
    if not pairs:
        return []  # no module declared an MCP server — the zone is empty

    ctx = McpServerContext(
        auth=McpServerTokenVerifier(_collect_resolver(modules)),
        audit=McpServerAuditMiddleware(),
        allowed_hosts=config.mcp_allowed_hosts_list,
    )
    # DNS-rebinding protection at the ASGI layer (the fork has no TransportSecuritySettings).
    asgi_mw = (
        [ASGIMiddleware(TrustedHostMiddleware, allowed_hosts=ctx.allowed_hosts)]
        if ctx.allowed_hosts
        else None
    )

    lifespans: list[AbstractAsyncContextManager[None]] = []
    built: dict[str, object] = {}
    for code, builder in pairs:
        if code in built:
            raise RuntimeError(f"mount_mcp_servers: duplicate mcp server code: {code!r}")
        mcp = builder(ctx)
        # path="/" — otherwise the sub-app listens on its default streamable_http_path="/mcp", and
        # under the /mcp/<code> mount the real endpoint drifts to /mcp/<code>/mcp (307→404).
        # With "/" the endpoint lands exactly on /mcp/<code> (strictly /mcp/<code>/ — Starlette
        # redirects the mount root to a trailing slash; the MCP client follows the 307).
        sub = mcp.http_app(
            path="/",
            transport="streamable-http",
            stateless_http=True,
            middleware=asgi_mw,
        )
        app.mount(f"{MCP_PREFIX}/{code}", sub)
        built[code] = mcp
        lifespans.append(sub.lifespan(sub))
        _LOG.info("mount_mcp_servers: mounted MCP server %r at %s/%s", code, MCP_PREFIX, code)

    # Live FastMCP instances on app.state — for introspection (an info page, if a
    # module adds one, reads them without rebuilding and without importing fastmcp).
    app.state.mcp_servers = built
    return lifespans


__all__ = ["MCP_PREFIX", "mount_mcp_servers"]
