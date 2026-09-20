"""MCP-тул удаления — одна дверь для всех типов, каскад выбирает сам код.

Пять отдельных тулов на одну строку кода каждый стоили бы агенту пяти описаний в контексте при
том, что отличается у них ровно одно — каскад, а он привязан к типу и описан здесь одним
списком.

Типы, у которых удаления нет, упираются в отказ, называющий причину и то, чем это делается
вместо. Отказ здесь не «нельзя», а обучающий канал: журнал дописываемый, раскладка принадлежит
человеку, необратимое остаётся ему же.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.modules.tasks.codes import bare_code, code_prefix
from src.modules.tasks.constants import (
    GROUP_CODE_PREFIX,
    NOTE_CODE_PREFIX,
    STAGE_CODE_PREFIX,
    TASK_CODE_PREFIX,
)
from src.modules.tasks.crud import stage as stage_crud
from src.modules.tasks.crud import task as task_crud
from src.modules.tasks.mcp.scope import require_scope
from src.modules.workspace.constants import WORKSPACE_CODE_PREFIX

if TYPE_CHECKING:  # fork fastmcp — только backend (через mcp_server(ctx))
    from fastmcp import FastMCP

_DELETABLE = (TASK_CODE_PREFIX, STAGE_CODE_PREFIX)

# Почему нельзя — по типу. Текст едет агенту как есть, поэтому он называет не запрет, а выход.
_REFUSALS = {
    NOTE_CODE_PREFIX: (
        "A journal entry is never deleted — the journal is append-only, and a history you can "
        "edit answers nothing. Changed your mind: write a new entry pointing at the old one."
    ),
    GROUP_CODE_PREFIX: (
        "Removing a group is the person's to do: the tasks filed there keep pointing at it, and "
        "bringing it back is theirs as well — you would leave them a hole you cannot undo. "
        "Re-word the theme with group_update, or empty it with tasks_regroup(group_code=\"\", …) "
        "and leave the empty group for them to clear."
    ),
    WORKSPACE_CODE_PREFIX: (
        "A workspace holds everything else here, and deleting it is the person's call. "
        "workspace_use switches the one you work in."
    ),
}


def register(mcp: "FastMCP") -> None:

    @mcp.tool()
    async def delete(code: str) -> bool:
        """Delete one entity. The code decides what goes, and what goes with it.

        TASK@ — the task and the whole branch under it, reversibly: it goes to the bin, and a
        person can bring it back. You cannot: restoring is theirs, so say so rather than
        creating a replacement.
        STAGE@ — removed outright. A plan has no hidden steps; a step you decided against is
        closed with stage_close(outcome="canceled"), which keeps why. Deleting leaves a gap in
        the numbering, and that is fine — numbers order the plan, they do not count it.

        A journal entry is not deletable, and neither is a group or a workspace.

        Args:
            code: The entity to delete — a TASK@ or STAGE@ code.
        """
        prefix = code_prefix(code)
        refusal = _REFUSALS.get(prefix)
        if refusal is not None:
            raise ValueError(refusal)
        if prefix not in _DELETABLE:
            raise ValueError(
                f"{code!r} is not something this deletes — pass a "
                f"{' or '.join(f'{p}@' for p in _DELETABLE)} code."
            )
        bare = bare_code(code, prefix) or ""
        await require_scope(prefix, bare)
        if prefix == TASK_CODE_PREFIX:
            return await task_crud.task_delete(bare)
        return await stage_crud.stage_delete(bare)


__all__ = ["register"]
