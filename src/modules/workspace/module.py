"""The ``workspace`` module — a workspace as the shared level of data isolation.

**Level 1**: depends only on the core and its modules, and refers to no application module.
Application modules (level 2 and above) depend on it: ``tasks`` keeps ``workspace_code`` on its
zones and tasks, the next module will keep it on its own rows — and each gains the ability to
narrow a query to the workspace the human is working in.

One table — ``workspaces``, without the module-name prefix: the module and the entity are one
and the same here, and ``workspace_workspace`` would be a stutter. The schema is built by the
``wkm_*`` migrations on portable types — the chain runs on both SQLite (dev) and PostgreSQL.
There are two revisions, and the split is not a matter of taste: the table is the target of a
cross-module FK, and ``depends_on`` is allowed only on a non-head, so the creating revision must
be buried under the next one (``wkm_002`` with the list index).

What lives inside a workspace the module does not know and must not know. Content counters for
the card are declared by the modules above — via ``stats.register_counter`` in their
``configure()``.

The HTTP API lives in the ``internal`` zone under the ``/workspace`` sub-prefix (``api.py``).
The sub-prefix is set explicitly rather than derived from ``name``: the module name is a Python
identifier with underscores, while a URL segment is hyphenated by project convention, and
deriving one from the other would break on the first two-word module.
"""

from __future__ import annotations

from pathlib import Path
from typing import ClassVar

from src.core.module import Module
from src.modules.workspace import models  # noqa: F401 — registers the models in Base.metadata
from src.modules.workspace.api import router
from src.modules.workspace.mcp.auth import resolve_mcp_token

_HERE = Path(__file__).resolve().parent


class WorkspaceModule(Module):
    name: ClassVar[str] = "workspace"
    description: ClassVar[str] = (
        "Workspaces: the top level of data isolation for the modules above."
    )
    migrations_dir = _HERE / "migrations" / "versions"
    internal_router = router
    internal_router_prefix = "/workspace"
    # The application's only MCP token resolver. It lives on the level 1 module on purpose: that
    # module sits below every application module and outlives any of them — why that matters,
    # see ``mcp/auth.py``. ``staticmethod`` is mandatory: access through an instance
    # (``m.mcp_token_resolver``) would bind the function as a method and pass ``self`` first.
    mcp_token_resolver = staticmethod(resolve_mcp_token)


__all__ = ["WorkspaceModule"]
