"""tasks — the module that stores tasks (groups, the task tree) inside a workspace.

A domain module for one developer and their executing agent, **level 2**: the workspace comes
from ``workspace``; its own are groups and tasks, whose hierarchy lives in the separate link table
``tasks_link``. The agent's tools over this data are the ``workbench`` module's, a level up.
"""

from src.modules.tasks.module import TasksModule

__all__ = ["TasksModule"]
