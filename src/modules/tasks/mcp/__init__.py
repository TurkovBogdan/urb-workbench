"""MCP-сервер ``workbench`` — один сервер на весь стенд: пространства и работа внутри них.

Сервер один, а тулы живут по модулям: пространство отдаёт свои из ``workspace/mcp/``, задачи —
свои отсюда. Собирает всё ``tasks``, потому что он уровнем выше и на ``workspace`` уже опирается;
обратной сборки быть не может — уровень 1 про задачи не знает.

``mcp_server(ctx)`` — конструктор (``McpServerBuilder``), кладётся в
``TasksModule.mcp_servers["workbench"]``. Импорт ``make_mcp_server`` (→ ``fastmcp``) ОТЛОЖЕН в
тело функции: объявление словаря в ``module.py`` ссылается на функцию, не вызывая её, →
``build_modules()`` не тянет форк. Регистрирующие модули держат ``FastMCP`` только под
``TYPE_CHECKING``.

**Резолвер токена мы не объявляем.** ``mount_mcp_servers._collect_resolver`` требует ровно
одного поставщика на всё приложение, и им работает ``workspace`` (``workspace/mcp/auth.py``,
заглушка до auth-модуля). Объявим второй — монтаж упадёт для всех, включая чужие серверы.

**Активное пространство.** Сервер ведёт его по подключению, а не по процессу: как и почему —
``workspace/mcp/session.py``. Для автора нового тула правило короткое: аргумента пространства у
тула быть не должно, а вместо него — ``require_active()`` или ``require_scope(prefix, bare)``,
если тул принимает чужой код.
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
    "CODES. Every entity has a code that says what it is — WORKSPACE@ (a workspace), GROUP@ (a "
    "standing theme inside one), TASK@, STAGE@ (a step of a task's plan), NOTE@ (a journal "
    "entry). Pass a code back whole, exactly as you received it; never invent one. A code from "
    "another workspace is refused by name rather than acted on quietly — that refusal means you "
    "are in the wrong workspace, not that the entity is missing.\n\n"
    "EVERY ANSWER NAMES ITS WORKSPACE. Read it. It is the only way to notice that you are "
    "working in the wrong one: a list of someone else's tasks looks exactly like a list of "
    "tasks.\n\n"
    "HOW WORK IS SHAPED. Three depths, and each adds one way of working. `simple` — a title and "
    "a goal, often a job for a person. `standard` — plus the brief the requester writes (context, "
    "constraints, criteria of done), the plan you write as prose after reading the code, and a "
    "journal of decisions, findings and facts. `extended` — plus STAGES: the plan broken into "
    "steps, each with its own state and its own evidence. Stages are what separates extended from "
    "standard, and they earn their keep only when the work outlasts one sitting; a standard task "
    "refuses them and says so.\n"
    "Two things are never yours to set: the brief of a task a person wrote, and the verdict on "
    "whether the work is accepted. Hand over at in_review and say what you did.\n\n"
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
    "subject) is edited by body_set / body_replace / body_set_section / body_add, which answer "
    "with the SEAM of the edit rather than the text you sent. Plus delete(code), one door for "
    "every type, and interface_open(code) to put something on the user's screen."
)


def mcp_server(ctx: "McpServerContext") -> "FastMCP":
    """Собрать MCP-сервер ``workbench``: пространства (модуль ниже) + работа внутри них."""
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
