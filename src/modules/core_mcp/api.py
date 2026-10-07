"""The "MCP servers" section — introspection of modules brought up as MCP servers.

A read-only surface: lists the MCP servers mounted by the core (``/mcp/<code>``) and returns
for each its name/version/instructions, the tool list and a ready stdio config to paste into
an MCP client. The source of truth is the live ``FastMCP`` instances that
``mount_mcp_servers`` puts into ``app.state.mcp_servers`` while building the server; we read
them duck-typed (``name``/``version``/``instructions``/``list_tools``), so the module does
NOT import ``fastmcp`` (the worker stays clean).

The ``/servers`` root is spelled out in the paths; the zone adds the ``/core-mcp`` prefix.
The internal zone in the bare core is ``allow_all`` — no guard needed.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Request
from pydantic import BaseModel

from src.core.api import ApiError

# The project root (…/src/modules/core_mcp/api.py → four levels up) — goes into
# `uv run --directory`, so a client with its own cwd still lands in the project.
_PROJECT_ROOT = Path(__file__).resolve().parents[3]

# A bare server code ("workbench") is indistinguishable from other servers in a client's MCP list.
_CLIENT_SERVER_NAME_PREFIX = "urb-"


class McpToolInfo(BaseModel):
    name: str
    description: str | None
    input_schema: dict | None
    output_schema: dict | None


class McpServerSummary(BaseModel):
    code: str
    name: str
    version: str | None
    instructions: str | None
    tool_count: int


class McpServerDetail(BaseModel):
    code: str
    name: str
    version: str | None
    instructions: str | None
    tools: list[McpToolInfo]
    # A ready JSON connection config as a string, for copying. The same for Claude Desktop
    # and Claude Code — both spawn the local stdio wrapper `app.py --mcp-stdio` (a light
    # daemon wrapper) that brings up the backend itself and bridges the calls.
    connection_config: str


router = APIRouter()


def _servers(request: Request) -> dict[str, Any]:
    """The registry of live MCP instances from ``app.state`` (empty if the zone is not mounted)."""
    return getattr(request.app.state, "mcp_servers", {})


async def _tools(mcp: Any) -> list[McpToolInfo]:
    """The server's tools via introspection (no middleware/auth — the bare list)."""
    return [
        McpToolInfo(
            name=t.name,
            description=t.description,
            input_schema=t.parameters,
            output_schema=t.output_schema,
        )
        for t in await mcp.list_tools(run_middleware=False)
    ]


def _uv_binary() -> str:
    """The absolute path to ``uv`` for the config (fallback — the bare name).

    MCP clients often start with a trimmed PATH, so an absolute path is more reliable than a
    bare ``uv`` (otherwise the client cannot find the binary → "Connection Failed").
    """
    return shutil.which("uv") or "uv"


def _stdio_config(code: str, pin_code: bool, token: str, workspace: str) -> str:
    """The connection config through the stdio wrapper (``app.py --mcp-stdio``).

    The client itself spawns a light daemon wrapper over stdio — it lazily brings up the
    backend and bridges tool calls to ``/mcp/<code>``. The shape is the same for Claude Desktop
    and Claude Code. ``uv run --directory <root>`` pins the project regardless of the client's
    cwd.

    **What goes as an argument and what as a variable is decided by visibility, not taste.**
    Command-line arguments are visible in ``ps`` to any process on the machine; environment
    variables are not. So ``MCP_TOKEN`` (the MCP servers' bearer) stays in ``env``, while the
    server code and the workspace go as arguments: there is no secret in them, and as
    arguments they read at a glance and sit right next to the role itself.

    The server code is pinned only when there are several servers: otherwise the shim takes
    the single mounted one by itself, and an extra argument would promise a choice that does
    not exist. The workspace gets here by the same "only when set" rule — an empty argument
    would look like a required field someone forgot to fill. Both override the installation's
    ``.env`` as a flag on top of it: a connection is not an installation, and configuring one
    must not leak into the other.

    **The ``--flag=value`` form, not two array elements.** argparse treats both the same, but
    in a config a human edits by hand a glued pair cannot fall apart: you cannot reorder,
    duplicate or lose half of it, because there are no halves. For ``--mcp-stdio`` this
    matters most — its value is optional, so an orphaned flag would not break but would
    silently change meaning to "pick the server yourself".
    """
    args = ["run", "--directory", str(_PROJECT_ROOT), "python", "src/app.py"]
    args.append(f"--mcp-stdio={code}" if pin_code else "--mcp-stdio")
    if workspace:
        args.append(f"--mcp-workspace={workspace}")
    server: dict[str, Any] = {"command": _uv_binary(), "args": args}
    if token:
        server["env"] = {"MCP_TOKEN": token}
    client_server_name = f"{_CLIENT_SERVER_NAME_PREFIX}{code}"
    return json.dumps({"mcpServers": {client_server_name: server}}, indent=2, ensure_ascii=False)


@router.get("/servers", response_model=list[McpServerSummary])
async def list_servers(request: Request) -> list[McpServerSummary]:
    """A summary of all mounted MCP servers (name/version/tool count)."""
    out: list[McpServerSummary] = []
    for code, mcp in _servers(request).items():
        out.append(
            McpServerSummary(
                code=code,
                name=mcp.name,
                version=mcp.version,
                instructions=mcp.instructions,
                tool_count=len(await mcp.list_tools(run_middleware=False)),
            )
        )
    out.sort(key=lambda s: s.code)
    return out


@router.get("/servers/{code}", response_model=McpServerDetail)
async def get_server(code: str, request: Request) -> McpServerDetail:
    """One server's details: instructions, tools and the connection config."""
    servers = _servers(request)
    mcp = servers.get(code)
    if mcp is None:
        raise ApiError.not_found(
            f"MCP server {code!r} not found", code="core_mcp.server.not_found", params={"code": code}
        )
    return McpServerDetail(
        code=code,
        name=mcp.name,
        version=mcp.version,
        instructions=mcp.instructions,
        tools=await _tools(mcp),
        connection_config=_stdio_config(
            code,
            pin_code=len(servers) > 1,
            token=request.app.state.config.mcp_token,
            workspace=request.app.state.config.mcp_workspace,
        ),
    )


__all__ = ["router"]
