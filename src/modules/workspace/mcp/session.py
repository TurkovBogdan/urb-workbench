"""The agent session's active workspace: whose it is and where it is kept.

**Why this is a separate layer at all.** The MCP client spawns the shim, the shim proxies calls
to a shared backend, and the backend is mounted ``stateless_http`` — it keeps no sessions and
serves all connections and the browser at once. So the "active workspace" can be kept neither in
a process variable (there is one for everyone, and a neighbouring session would overwrite it)
nor in the MCP session (there is none here). The only thing that tells one connection from
another is the header the shim made up for itself at startup (``core/mcp_headers``).

**Where the binding is kept.** In ``core_modules_state`` under the session key — i.e. in the
database, not in memory. The shim survives a backend restart (they are separate processes), and
a binding in memory would vanish mid-work: an agent that picked a workspace an hour ago would
suddenly get "not chosen". Rows are cheaper than any table: the store already exists, no
migration needed.

**Three levels of resolution**, strongest to weakest: this session's binding → the workspace
from the launch config (the default header) → refusal. So a project with its own ``.mcp.json``
starts already bound, while ``workspace_use`` overrides the config only for its own session and
does not touch the file.

**A call without HTTP** (the in-memory ``Client`` in tests, a direct call from code) has no
headers at all. Such a call gets one shared key, ``_LOCAL_SESSION`` — not an error: no HTTP is
not a broken client but a different way of calling. A live header always beats this key, and
that is exactly what the test over the mounted server checks.
"""

from __future__ import annotations

from datetime import timedelta

from src.core.module_state import module_store
from src.core.utils.date import utc_now
from src.modules.workspace.codes import bare_code, strip_prefix
from src.modules.workspace.constants import WORKSPACE_CODE_PREFIX
from src.modules.workspace.crud import workspace as workspace_crud
from src.modules.workspace.mcp.errors import no_active_workspace
from src.modules.workspace.models.workspace import Workspace

_STORE = module_store("workspace")

# The key prefix in the module's shared store: the rest of ``workspace``'s state lives there too,
# and without it the session bindings would mix with it in one namespace.
_KEY_PREFIX = "mcp_session:"

# The key for a call that did not come over HTTP. The name is deliberately telling: seeing it in
# the database, a reader understands it is not somebody's session but a shared box for calls
# without a header.
_LOCAL_SESSION = "local"

# How long an abandoned binding lives. Agent sessions last hours, so a month means "never gets in
# the way"; cleanup exists only so the table does not grow forever with every launch.
_TTL = timedelta(days=30)


def _headers() -> dict[str, str]:
    """The current HTTP request's headers; outside a request — empty, no exception.

    ``fastmcp`` is imported inside the function body: this module is also pulled in where the
    fork must not be.
    """
    from fastmcp.server.dependencies import get_http_headers

    return get_http_headers()


def session_id() -> str:
    """The session key: the identifier from the header, otherwise the shared local box."""
    from src.core.mcp_headers import MCP_SESSION_HEADER

    return _headers().get(MCP_SESSION_HEADER) or _LOCAL_SESSION


def _default_code() -> str | None:
    """The workspace from the launch config (the default header), already as a bare code.

    A foreign prefix here is ignored rather than refused: the value comes from the user's
    settings file, and failing the whole server over a typo in it would make an optional setting
    mandatory. The agent will see a missing default as the ordinary "no workspace chosen".
    """
    from src.core.mcp_headers import MCP_WORKSPACE_HEADER

    raw = _headers().get(MCP_WORKSPACE_HEADER)
    if not raw:
        return None
    try:
        return bare_code(raw, WORKSPACE_CODE_PREFIX)
    except ValueError:
        return None


async def bound_code() -> str | None:
    """The code of the workspace bound to this session (ignoring the default).

    Folded through ``strip_prefix`` on the way out: bindings written before codes went upper
    case still hold the lower-case hash, and the store is not migrated with the tables.
    """
    row = await _STORE.get(_KEY_PREFIX + session_id())
    return strip_prefix(row.get("workspace")) if isinstance(row, dict) else None


async def active_code() -> str | None:
    """The active workspace's bare code: the session binding, else the default, else ``None``."""
    return await bound_code() or _default_code()


async def bind(workspace_code: str) -> None:
    """Bind the session to a workspace. The timestamp lets abandoned bindings be cleaned up."""
    await _STORE.set(
        _KEY_PREFIX + session_id(),
        {"workspace": workspace_code, "at": utc_now().isoformat()},
    )


async def require_active() -> Workspace:
    """The active workspace as a row, or a refusal with the way to fix it.

    The workspace is read from the database rather than trusting the code: the binding may have
    been set a week ago and the workspace deleted since. A deleted one is returned too: its tasks
    have not gone anywhere, and "not found" over live data would be a lie. Gone entirely — that
    is the same "pick a workspace", because it is fixed the same way.
    """
    code = await active_code()
    row = (
        await workspace_crud.workspace_get(code, include_deleted=True) if code else None
    )
    if row is None:
        raise no_active_workspace()
    return row


async def prune() -> int:
    """Remove bindings older than ``_TTL``; return how many were removed.

    Called on binding, not on a schedule: cleanup is rarely needed, and an extra scheduler job
    for a dozen rows would be an organ with nothing to feed it.
    """
    edge = utc_now() - _TTL
    stale = [
        key
        for key, value in (await _STORE.all()).items()
        if key.startswith(_KEY_PREFIX)
        and isinstance(value, dict)
        and str(value.get("at", "")) < edge.isoformat()
    ]
    for key in stale:
        await _STORE.delete(key)
    return len(stale)


__all__ = [
    "active_code",
    "bind",
    "bound_code",
    "prune",
    "require_active",
    "session_id",
]
