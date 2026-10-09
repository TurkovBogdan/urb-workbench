"""The MCP surface of the ``workspace`` module — tools and the active-workspace mechanics.

The module declares no MCP server of its own: there is one server for the whole installation
(``workbench``), and it is assembled by the module a level above — ``tasks``, which relies on
``workspace`` anyway. Hence the package rule: the TOOLS and the session state live here, while
the server's assembly and instructions do not. The dependency thus stays one-way: ``tasks`` knows
about the workspace, the workspace does not know about tasks.

No file in the package imports ``fastmcp`` at the top level (``FastMCP`` only under
``TYPE_CHECKING``, ``get_http_headers`` inside a function body): the package must stay safe for
the worker, like everything else outside ``src/core/mcp``.
"""

from __future__ import annotations

from src.modules.workspace.mcp.workspace import register

__all__ = ["register"]
