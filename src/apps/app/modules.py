"""The module set of the ``apps/app`` application.

The single source of the module list: both the app assembly (``server.py``) and the
standalone migration run (``app.py migrate``) reuse it, so that ``version_locations``
match what the server actually brings up.
"""

from __future__ import annotations

from src.core.module import Module
from src.modules.core_changes import CoreChangesModule
from src.modules.core_interface import CoreInterfaceModule
from src.modules.core_mcp import CoreMcpModule
from src.modules.core_monitoring import CoreMonitoringModule
from src.modules.core_setup import CoreSetupModule
from src.modules.tasks import TasksModule
from src.modules.workspace import WorkspaceModule


def build_modules() -> list[Module]:
    """The application's modules in registration order.

    On top of the core (``src/core``: migrations, scheduler, router zones, SPA serving,
    settings store) sit ``core_setup`` — the ENV settings page (editing ``.env``
    + restart), ``core_interface`` — user interface settings (theme, typefaces,
    document and diagram styling), ``core_monitoring`` — the jobs section (list +
    runs + logs, read-only), ``core_mcp`` — introspection of the modules mounted as MCP servers
    (read-only), ``core_changes`` — the data change feed behind the interface's live updates,
    ``workspace`` — workspaces (the shared data isolation level)
    and ``tasks`` — the task store inside a workspace (groups, task tree, plan and journal).
    A new module — add an instance to the list.

    **The order is dependencies, not taste.** A level-1 module (``workspace``) comes before the
    ones that reference it: the ``configure()`` of the modules above registers their counters in
    it, and there is nothing to register into in a module not yet built. Between other modules'
    migration branches the order is set not by this list but by ``depends_on`` in the revisions
    themselves.
    """
    return [
        CoreSetupModule(),
        CoreInterfaceModule(),
        CoreMonitoringModule(),
        CoreMcpModule(),
        # Before the data modules: they declare their entities in it from their ``configure()``.
        CoreChangesModule(),
        WorkspaceModule(),
        TasksModule(),
    ]


__all__ = ["build_modules"]
