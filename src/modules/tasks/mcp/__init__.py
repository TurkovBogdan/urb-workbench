"""The ``workbench`` MCP server — one server per installation: workspaces and the work inside them.

There is one server, but the tools live by module: the workspace contributes its own from
``workspace/mcp/``, tasks contributes its own from here. ``tasks`` assembles the whole thing
because it is a level higher and already depends on ``workspace``; the reverse assembly is
impossible — level 1 knows nothing about tasks.

``mcp_server(ctx)`` is the builder (``McpServerBuilder``), placed in
``TasksModule.mcp_servers["workbench"]``. The ``make_mcp_server`` import (→ ``fastmcp``) is
DEFERRED into the function body: the dict declaration in ``module.py`` references the function
without calling it, → ``build_modules()`` does not pull in the fork. Registering modules hold
``FastMCP`` only under ``TYPE_CHECKING``.

**We do not declare a token resolver.** ``mount_mcp_servers._collect_resolver`` requires exactly
one provider for the whole application, and ``workspace`` serves as that provider
(``workspace/mcp/auth.py``, a stub until there is an auth module). Declare a second one and
mounting fails for everyone, other modules' servers included.

**The active workspace.** The server tracks it per connection, not per process — how and why is
in ``workspace/mcp/session.py``. For the author of a new tool the rule is short: a tool must not
take a workspace argument; instead it calls ``require_active()``, or
``require_scope(prefix, bare)`` if the tool accepts an entity code that could belong to another
workspace.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.modules.tasks.mcp.body import register as _register_body
from src.modules.tasks.mcp.delete import register as _register_delete
from src.modules.tasks.mcp.group import register as _register_group
from src.modules.tasks.mcp.interface import register as _register_interface
from src.modules.tasks.mcp.note import register as _register_note
from src.modules.tasks.mcp.skill import register as _register_skill
from src.modules.tasks.mcp.stage import register as _register_stage
from src.modules.tasks.mcp.task import register as _register_task
from src.modules.workspace.mcp import register as _register_workspace

if TYPE_CHECKING:
    from fastmcp import FastMCP

    from src.core.mcp import McpServerContext

_INSTRUCTIONS = (
    "Workbench MCP server — the developer's own workspaces and the work inside them.\n\n"
    "WORKSPACE FIRST. Everything here lives inside a workspace, and nothing reads across "
    "workspaces: it is what keeps work apart from personal, one client apart from another. This "
    "session works in exactly one, and no tool takes it as an argument — you set it once. If a "
    "tool answers that nothing is bound yet, call workspaces_list() to see what exists and "
    "workspace_use(workspace_code) to pick one. Some connections are already configured with a "
    "workspace; workspaces_list() marks the active one either way.\n"
    "The binding is yours alone — a second agent working elsewhere does not move it, and it "
    "lasts as long as this connection.\n\n"
    "CODES. Every entity has a code that says what it is — WORKSPACE@ (a workspace), TASKGROUP@ "
    "(a standing theme inside one), TASK@, STAGE@ (a step of a task's plan), NOTE@ (a journal "
    "entry). Pass a code back whole, exactly as you received it; never invent one. A code from "
    "another workspace is refused by name rather than acted on quietly — that refusal means you "
    "are in the wrong workspace, not that the entity is missing.\n\n"
    "EVERY ANSWER NAMES ITS WORKSPACE. Read it. It is the only way to notice that you are "
    "working in the wrong one: a list of someone else's tasks looks exactly like a list of "
    "tasks.\n\n"
    "HOW WORK IS SHAPED. Three depths, and each adds one way of working. `simple` — a title, "
    "a goal and the context, often a job for a person. `standard` — plus the rest of the brief "
    "(constraints, criteria of done), the plan you write as prose after reading the code, and a "
    "journal of decisions, findings and facts. `extended` — plus STAGES: the plan broken into "
    "steps, each with its own state and its own evidence. Stages are what separates extended from "
    "standard, and they earn their keep only when the work outlasts one sitting; a standard task "
    "refuses them and says so.\n"
    "The brief is yours to fill in and correct on any task, including one a person set — when you "
    "change theirs, say what and why in a decision note. The verdict on whether the work is "
    "accepted is never yours: hand over at in_review and say what you did.\n\n"
    "THE LAYOUT IS THEIRS, THE HANDS ARE YOURS. Groups are how the person sees their own work, "
    "and you can make and re-word them — on request. Make one when they ask for it, not because "
    "the backlog looks untidy to you: three themes they recognise beat seven you invented. "
    "Deleting a group stays theirs, because undoing it is theirs.\n\n"
    "SKILLS. This server carries its own reference material — how it expects a brief, a plan "
    "and a journal to be written, and what its interface actually renders. skills_list() names "
    "what is available; skill_get(name, section?) returns it. Read skill_get('task-brief') "
    "before writing a brief and skill_get('task-plan') before planning: those are conventions "
    "of this app, not things to infer.\n\n"
    "TOOLS. Space: workspaces_list, workspace_use. Layout: groups_list, group_create, "
    "group_update, tasks_regroup. Work: tasks_list, task_get, "
    "task_create, task_update, task_status. Plan: stage_add, stage_update, stage_close. "
    "Journal: note_add, note_resolve, notes_list. Long text (a plan, a stage body, an entry's "
    "subject) is edited by body_set / body_replace / body_set_section / body_add. None of them "
    "echoes the text you sent: body_replace and body_add answer with the SEAM of the edit, "
    "body_set_section with what it CUT, body_set with the new length. Plus delete(code), one "
    "door for every type, and interface_open(code) to put something on the user's screen."
)


def mcp_server(ctx: "McpServerContext") -> "FastMCP":
    """Build the ``workbench`` MCP server: workspaces (the module below) + the work inside them."""
    from src.core.mcp import make_mcp_server

    mcp = make_mcp_server("workbench", _INSTRUCTIONS, ctx)
    _register_workspace(mcp)
    _register_group(mcp)
    _register_task(mcp)
    _register_stage(mcp)
    _register_note(mcp)
    _register_body(mcp)
    _register_delete(mcp)
    _register_skill(mcp)
    _register_interface(mcp)
    return mcp


__all__ = ["mcp_server"]
