"""The ``workbench`` module — everything the agent sees, and nothing the data needs.

**Level 3.** Two surfaces sit on one set of data, and they are split by level: a domain module
(``workspace``, ``notes``, ``tasks``) owns its rows, its rules — what may and may not happen to
them (``rules.py``) — and the person's HTTP API; this module owns what the agent sees: tool names
and arguments, answers, refusal texts, the server instructions, the skills. It imports the
modules below, they never import it — ``tests/apps/test_python_layer_boundaries.py`` holds that.

A new domain arrives here with its own tools and its own handlers for the shared methods
(``content_*``, ``delete``, ``interface_open``, the workspace fence) — registered by code prefix,
without touching a neighbour's domain module.

No tables, no migrations, no HTTP routes: the module is the server and nothing else. Its place is
last in ``build_modules``, after every module whose data it serves; the core mounts its server
after every ``configure()``, so the order is a statement of dependency, not a requirement of the
mount.

**The application's only MCP token resolver is here** (``auth.py``): ``mount_mcp_servers`` takes
exactly one for the whole application, and the gate belongs with the servers it guards.
"""

from __future__ import annotations

from typing import ClassVar

from src.core.module import Module
from src.modules.workbench.auth import resolve_mcp_token
from src.modules.workbench.server import mcp_server


class WorkbenchModule(Module):
    name: ClassVar[str] = "workbench"
    description: ClassVar[str] = (
        "The agent surface: the workbench MCP server over workspaces, notes and tasks."
    )
    # The value is a FUNCTION, not a built server: the dict is declared at module import, and an
    # instance here would drag ``fastmcp`` into every process, the worker included.
    mcp_servers = {"workbench": mcp_server}
    # ``staticmethod`` is mandatory: access through an instance (``m.mcp_token_resolver``) would
    # bind the function as a method and pass ``self`` first.
    mcp_token_resolver = staticmethod(resolve_mcp_token)


__all__ = ["WorkbenchModule"]
