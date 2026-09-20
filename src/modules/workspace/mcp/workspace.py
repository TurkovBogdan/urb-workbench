"""MCP-тулы пространства — два: посмотреть, что есть, и выбрать, в чём работать.

Заводить, править и удалять пространства агенту не отдаётся: пространство — раскладка человека,
а не результат работы, и живёт она в интерфейсе (см. ``workspace/MODULE.md``). Отсюда поверхность
из двух инструментов вместо семи.

Оба инструмента — единственные, кто **не** ограничен активным пространством: одному надо показать
все, другой его и назначает. Всё остальное на сервере через этот забор проходит.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.modules.workspace import stats
from src.modules.workspace.codes import bare_code, tagged
from src.modules.workspace.constants import WORKSPACE_CODE_PREFIX
from src.modules.workspace.crud import workspace as workspace_crud
from src.modules.workspace.dto import AgentWorkspaceBound, AgentWorkspaceRow
from src.modules.workspace.mcp import session

if TYPE_CHECKING:  # fork fastmcp — только backend (через mcp_server(ctx))
    from fastmcp import FastMCP

_BIND_NOTE = (
    "Bound for this connection only — a fresh connection starts unbound and you pick again. "
    "To make a project always open in this workspace, set MCP_WORKSPACE to this code in the "
    "env block of its MCP client config."
)


def register(mcp: "FastMCP") -> None:

    @mcp.tool()
    async def workspaces_list() -> list[AgentWorkspaceRow]:
        """List the workspaces and show which one this session works in.

        A workspace is the top-level boundary of everything else here: groups and tasks live
        inside one, and nothing on this server reads across them. Call this first when you do not
        know where you are — the row with `active: true` is the one your other calls will hit,
        and if no row has it, nothing is bound yet.

        Counters say what is inside each one, so you can tell the working space from the empty
        one without opening it.
        """
        rows = await workspace_crud.workspace_list()
        counted = await stats.counts_for([row.code for row in rows])
        active = await session.active_code()
        return [
            AgentWorkspaceRow(
                code=row.code,
                title=row.title,
                description=row.description,
                counters=counted.get(row.code, {}),
                active=row.code == active,
            )
            for row in rows
        ]

    @mcp.tool()
    async def workspace_use(workspace_code: str) -> AgentWorkspaceBound:
        """Bind this session to a workspace — after this, no tool takes a workspace argument.

        This is the first call of a session unless the connection was configured with one. Every
        workspace-scoped tool then works inside what you picked, and a code from any other
        workspace is refused by name rather than silently acted on.

        The binding belongs to this connection: a second agent working in another workspace does
        not move yours, and yours does not move theirs.

        Args:
            workspace_code: The workspace to work in — a WORKSPACE@ code from workspaces_list.
        """
        bare = bare_code(workspace_code, WORKSPACE_CODE_PREFIX) or ""
        row = await workspace_crud.workspace_get(bare)
        if row is None:
            raise ValueError(
                f"Workspace {workspace_code} does not exist (or was deleted). "
                "workspaces_list() shows the ones you can pick."
            )
        await session.bind(row.code)
        # Уборка брошенных привязок — здесь: она нужна раз в месяц, и вешать ради неё задачу
        # планировщика значит завести орган, который нечем кормить.
        await session.prune()
        counted = await stats.counts_for([row.code])
        return AgentWorkspaceBound(
            code=row.code,
            title=row.title,
            description=row.description,
            counters=counted.get(row.code, {}),
            active=True,
            note=_BIND_NOTE.replace("this code", str(tagged(WORKSPACE_CODE_PREFIX, row.code))),
        )


__all__ = ["register"]
