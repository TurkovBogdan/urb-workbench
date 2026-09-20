"""MCP-тул групп — один: посмотреть раскладку активного пространства.

Правку групп агенту не отдаём: раскладка — дело человека, как и сами пространства. Чтения
одной группы тоже нет — ``groups_list`` несёт ровно те же поля, и отдельный ``group_get``
отличался бы от него только тем, что возвращает одну строку вместо трёх.

Описание группы здесь рабочее поле, а не украшение: в нём границы темы, и по ним агент решает,
куда класть задачу.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.modules.tasks.crud import group as group_crud
from src.modules.tasks.crud import task as task_crud
from src.modules.tasks.dto import AgentGroupList, AgentGroupRow
from src.modules.tasks.mcp.scope import require_active

if TYPE_CHECKING:  # fork fastmcp — только backend (через mcp_server(ctx))
    from fastmcp import FastMCP


def register(mcp: "FastMCP") -> None:

    @mcp.tool()
    async def groups_list() -> AgentGroupList:
        """List the groups of the workspace this session works in.

        A group is a standing theme inside a workspace — billing, interface, infrastructure —
        and a task may sit in one or in none. Read the descriptions before filing a task: they
        say where the boundary of each group runs, which the titles alone do not.

        Takes no workspace: the session is already bound to one. If it is not, this call tells
        you so and names how to fix it.
        """
        active = await require_active()
        rows = await group_crud.group_list_by_workspace(active.code)
        counted = await task_crud.task_count_by_group_codes([row.code for row in rows])
        return AgentGroupList(
            workspace=active.code,
            workspace_title=active.title,
            groups=[
                AgentGroupRow(
                    code=row.code,
                    title=row.title,
                    description=row.description,
                    task_count=counted.get(row.code, 0),
                )
                for row in rows
            ],
        )


__all__ = ["register"]
