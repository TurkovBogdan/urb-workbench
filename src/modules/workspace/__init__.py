"""workspace — a workspace as the shared level of data isolation (a level 1 module).

Holds one entity and an extension point for it: the modules above refer to a workspace by their
``workspace_code`` and declare content counters for its card (``stats``).
"""

from src.modules.workspace.module import WorkspaceModule

__all__ = ["WorkspaceModule"]
