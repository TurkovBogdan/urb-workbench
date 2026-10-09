"""The ``tasks`` module — task storage for one developer and their executing agent.

**Level 2**: on top of the core and on top of ``workspace``. The workspace is not ours — groups
and tasks hold a ``workspace_code`` pointing at it, and no query crosses workspaces. There is no
reverse dependency and cannot be: the lower-level module knows nothing about tasks.

Five tables: ``tasks_group`` → ``tasks`` (the task itself, named after the module — ``tasks_task``
would be a stutter), the task's place in the tree is split out into ``tasks_link`` (an edge:
parent + position), and the work plan into ``tasks_stage`` (stages) and ``tasks_journal``
(journal). The schema is built by ``tsm_*`` migrations on portable types — the chain runs on both
SQLite (dev) and PostgreSQL. It starts at ``tsm_001_group``: the module does not create the
workspace table — it belongs to ``workspace``, and our first revision only declares
``depends_on`` on it, because an FK target must exist before the reference.

Two surfaces sit on top of the data layer. HTTP in the ``internal`` zone (``api.py``, subprefix
``/workbench``) — called by the UI, it takes the workspace as a parameter. The ``workbench`` MCP
server (``mcp/``) — called by the agent, which picks the workspace once per connection, after
which no tool accepts it. This module assembles the server, but the workspace's own tools come
from ``workspace/mcp/``: there is one server per installation, and ownership of an entity does
not move.

**Counters for the workspace card are registered here.** How many groups and tasks a workspace
holds is this module's knowledge, but the workspaces page is what must show it; so we put two
counting functions and label keys into the ``workspace.stats`` registry, and the lower-level
module builds its list row from what was declared. Registration happens in ``configure()`` — it
is called once per app build, before the first request, and a rebuild (tests) overwrites the
entry by key.

The subprefix is set explicitly rather than derived from ``name``: a module name is a Python
identifier with underscores, while a URL segment is hyphenated by project convention, and deriving
one from the other would break on the first two-word module.

**Why ``/workbench`` and not ``/tasks``.** The core module ``core_monitoring`` is mounted without
a prefix (``internal_router_prefix = ""``) and owns ``/tasks`` and ``/tasks/{module}/{code}`` at
the zone root — the scheduler's schedule. With our ``/tasks`` subprefix, a task address
(``/internal/tasks/tasks/{code}``) fell into its two-segment route and answered
``{"error": "task not registered"}``: the detail view did not work at all. The core is not ours,
so our module moved. Only the external HTTP prefix was renamed — the module name, tables and codes
are unchanged.
"""

from __future__ import annotations

from pathlib import Path
from typing import ClassVar

from fastapi import FastAPI

from src.core.config import Config
from src.core.module import Module
from src.modules.core_changes import ChangeEntity, Code, register_entity
from src.modules.tasks import models  # noqa: F401 — registers the models in Base.metadata
from src.modules.tasks.api import router
from src.modules.tasks.mcp import mcp_server
from src.modules.tasks.crud import group as group_crud
from src.modules.tasks.crud import task as task_crud
from src.modules.tasks.constants import (
    GROUP_CODE_PREFIX,
    JOURNAL_CODE_PREFIX,
    NOTE_CODE_PREFIX,
    STAGE_CODE_PREFIX,
    TASK_CODE_PREFIX,
)
from src.modules.workspace.constants import WORKSPACE_CODE_PREFIX
from src.modules.workspace.stats import WorkspaceCounter, register_counter

# What the change feed (``core_changes``) sees of this module. The names are a public contract
# with the frontend (``web/src/features/tasks``): renaming here changes an address, not an internal
# detail. The refs are exactly those by which a screen recognises "this is about me": the list by
# workspace and group, the task page by its own task, and a journal entry also by stage.
CHANGE_ENTITIES = (
    ChangeEntity(
        "tasks.task",
        models.TasksTask,
        id=Code("code", TASK_CODE_PREFIX),
        refs=(Code("workspace_code", WORKSPACE_CODE_PREFIX), Code("group_code", GROUP_CODE_PREFIX)),
    ),
    # A tree edge: the task's place among its siblings and its parent. The edge has no code of its
    # own — it is named by the task whose place it describes.
    ChangeEntity(
        "tasks.link",
        models.TasksLink,
        id=Code("task_code", TASK_CODE_PREFIX),
        refs=(Code("parent_code", TASK_CODE_PREFIX),),
    ),
    ChangeEntity(
        "tasks.group",
        models.TasksGroup,
        id=Code("code", GROUP_CODE_PREFIX),
        refs=(Code("workspace_code", WORKSPACE_CODE_PREFIX),),
    ),
    ChangeEntity(
        "tasks.stage",
        models.TasksStage,
        id=Code("code", STAGE_CODE_PREFIX),
        refs=(Code("task_code", TASK_CODE_PREFIX),),
    ),
    ChangeEntity(
        "tasks.journal",
        models.TasksJournal,
        id=Code("code", JOURNAL_CODE_PREFIX),
        refs=(Code("task_code", TASK_CODE_PREFIX), Code("stage_code", STAGE_CODE_PREFIX)),
    ),
    # A task note's link: which task holds the document. Edits of the document itself come as
    # ``notes.note`` from its own module; this says the task's list changed.
    ChangeEntity(
        "tasks.note",
        models.TasksNote,
        id=Code("note_code", NOTE_CODE_PREFIX),
        refs=(Code("task_code", TASK_CODE_PREFIX),),
    ),
)

_HERE = Path(__file__).resolve().parent


class TasksModule(Module):
    name: ClassVar[str] = "tasks"
    description: ClassVar[str] = (
        "Tasks: groups and a task tree with priorities and deadlines inside a workspace."
    )
    migrations_dir = _HERE / "migrations" / "versions"
    internal_router = router
    internal_router_prefix = "/workbench"
    # The value is a FUNCTION, not a built server: the dict is declared at module import, and an
    # instance here would drag ``fastmcp`` into every process, the worker included.
    # ``mcp_token_resolver`` is deliberately NOT set — the ``mcp/__init__`` docstring says why.
    mcp_servers = {"workbench": mcp_server}

    def configure(self, app: FastAPI, config: Config) -> None:
        """Tell the workspace what we keep in it — and how to count it; tell the change feed what
        of it the frontend sees (``CHANGE_ENTITIES``).

        Groups come before tasks (``sort``): on the card the layout reads first, then what fills
        it. The label keys are ours — renaming "group" is edited where the entity lives, not in a
        module that knows nothing about it.
        """
        register_counter(
            WorkspaceCounter(
                key="groups",
                label_key="tasks.workspace.counter.groups",
                count_by_codes=group_crud.group_count_by_workspace_codes,
                sort=600,
            )
        )
        register_counter(
            WorkspaceCounter(
                key="tasks",
                label_key="tasks.workspace.counter.tasks",
                count_by_codes=task_crud.task_count_by_workspace_codes,
                sort=500,
            )
        )
        for entity in CHANGE_ENTITIES:
            register_entity(entity)


__all__ = ["TasksModule"]
