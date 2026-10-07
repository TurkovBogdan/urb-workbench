"""tasks — the module that stores tasks (groups, the task tree) inside a workspace.

A domain module for one developer and their executing agent, **level 2**: the workspace comes
from ``workspace``; its own are groups and tasks, whose hierarchy lives in the separate link table
``tasks_link``. There is no MCP surface yet.
"""

from src.modules.tasks.module import TasksModule

__all__ = ["TasksModule"]
