"""The module set of the ``apps/app`` application.

The single source of the module list: both the app assembly (``server.py``) and the
standalone migration run (``app.py migrate``) reuse it, so that ``version_locations``
match what the server actually brings up.
"""

from __future__ import annotations

from src.core.module import Module
from src.modules.codex import CodexModule
from src.modules.core_changes import CoreChangesModule
from src.modules.core_interface import CoreInterfaceModule
from src.modules.core_lookup import CoreLookupModule
from src.modules.core_mcp import CoreMcpModule
from src.modules.core_monitoring import CoreMonitoringModule
from src.modules.core_setup import CoreSetupModule
from src.modules.core_storage import CoreStorageModule
from src.modules.core_storage_upload import CoreStorageUploadModule
from src.modules.core_storage_view import CoreStorageViewModule
from src.modules.core_transfer import CoreTransferModule
from src.modules.notes import NotesModule
from src.modules.tasks import TasksModule
from src.modules.workbench import WorkbenchModule
from src.modules.workspace import WorkspaceModule


def build_modules() -> list[Module]:
    """The application's modules in registration order.

    On top of the core (``src/core``: migrations, scheduler, router zones, SPA serving,
    settings store) sit ``core_setup`` — the ENV settings page (editing ``.env``
    + restart), ``core_interface`` — user interface settings (theme, typefaces,
    document and diagram styling), ``core_monitoring`` — the jobs section (list +
    runs + logs, read-only), ``core_mcp`` — introspection of the modules mounted as MCP servers
    (read-only), ``core_changes`` — the data change feed behind the interface's live updates,
    ``core_lookup`` — what an entity code stands for, for codes of any module, ``core_storage`` —
    registration and physical storage of files, ``core_storage_upload`` — taking files in from the
    person and the agent (a request body, a server path, an upload address with a signed token),
    ``core_storage_view`` — serving those files over HTTP, ``core_transfer`` — what every export
    and import of an entity between installations shares (the archive, conflicts of codes, files
    under their codes), ``workspace`` — workspaces (the shared data isolation level), ``notes`` — markdown documents
    with no owner, which the modules above link to,
    ``tasks`` — the task store inside a workspace (groups, task tree, plan and journal),
    ``codex`` — development rules shared across projects, mounted into workspaces, and
    ``workbench`` — the agent surface over all of them: the ``workbench`` MCP server.
    A new module — add an instance to the list.

    **The order is dependencies, not taste.** Level-1 modules (``workspace``, ``notes``) come
    before the ones that reference them: the ``configure()`` of the modules above registers their
    counters in the workspace, and there is nothing to register into in a module not yet built.
    ``workbench`` (level 3) is last: it serves every domain module below it. Between other modules'
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
        # Before the data modules too: they register their code prefixes in it.
        CoreLookupModule(),
        # The stores are folders inside ``AppPath.storage``; the consumers above keep files there.
        CoreStorageModule(stores=["public", "private"]),
        # Takes files in under ``/storage/upload`` and hands them to the holders registered in it
        # by the data modules' ``configure()``.
        CoreStorageUploadModule(),
        # Serves the ``public`` store under ``/storage``.
        CoreStorageViewModule(),
        # The shared part of exporting and importing an entity; ``tasks`` and ``codex`` build on it.
        CoreTransferModule(),
        WorkspaceModule(),
        NotesModule(),
        TasksModule(),
        CodexModule(),
        WorkbenchModule(),
    ]


__all__ = ["build_modules"]
