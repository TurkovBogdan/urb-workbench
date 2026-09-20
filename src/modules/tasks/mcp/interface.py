"""MCP-тул показа — открыть страницу сущности в браузере пользователя.

Единственный мост «агент → глаза человека»: код превращается в адрес страницы приложения и
открывается локальным браузером. Приложение локальное, бэкенд раздаёт собранный SPA сам, поэтому
адрес строится от ``server_host``/``server_port`` — тот же базовый url, что открывает stdio-шим.

Своей страницы есть не у всего. Этап и запись журнала живут на странице задачи, и код такого
типа ведёт туда же — резолвим владельца и открываем его. Отказывать тут было бы буквоедством:
агент просит показать работу, а не адрес.

Забор пространства действует и здесь. Открытие страницы — видимое действие на машине человека, и
показать ему чужой контур молча значило бы сделать ошибку контура ещё и заметной не тому.
"""

from __future__ import annotations

import asyncio
import webbrowser
from typing import TYPE_CHECKING

from src.core.config import get_config
from src.modules.tasks.codes import bare_code, code_prefix, tagged
from src.modules.tasks.constants import (
    GROUP_CODE_PREFIX,
    NOTE_CODE_PREFIX,
    STAGE_CODE_PREFIX,
    TASK_CODE_PREFIX,
)
from src.modules.tasks.crud import note as note_crud
from src.modules.tasks.crud import stage as stage_crud
from src.modules.tasks.mcp.scope import require_scope
from src.modules.workspace.constants import WORKSPACE_CODE_PREFIX

if TYPE_CHECKING:  # fork fastmcp — только backend (через mcp_server(ctx))
    from fastmcp import FastMCP

# Списочные страницы: у пространства и группы своей карточки-страницы нет, они живут строками в
# своих списках. Открываем список — это и есть «покажи, где оно».
_LIST_PAGE = {
    WORKSPACE_CODE_PREFIX: "/workspaces",
    GROUP_CODE_PREFIX: "/tasks/groups",
}

_OPENABLE = (
    WORKSPACE_CODE_PREFIX,
    GROUP_CODE_PREFIX,
    TASK_CODE_PREFIX,
    STAGE_CODE_PREFIX,
    NOTE_CODE_PREFIX,
)


async def _owning_task(prefix: str, bare: str) -> str:
    """Задача, которой принадлежит этап или запись журнала."""
    if prefix == STAGE_CODE_PREFIX:
        row = await stage_crud.stage_get(bare)
    else:
        row = await note_crud.note_get(bare)
    if row is None:
        raise ValueError(f"{tagged(prefix, bare)} does not exist.")
    return row.task_code


def _app_url(path: str) -> str:
    config = get_config()
    host = config.server_host if config.server_host not in ("", "0.0.0.0") else "127.0.0.1"
    return f"http://{host}:{config.server_port}{path}"


def register(mcp: "FastMCP") -> None:

    @mcp.tool()
    async def interface_open(code: str) -> str:
        """Open the page for a code in the user's browser and return its address.

        This is how you SHOW something instead of describing it. Use it when the user asks to
        see something, and when you have finished a piece of work worth looking at — it puts the
        thing on screen rather than a paragraph about it. Returning the address also lets you
        paste it into the conversation.

        A STAGE@ or a NOTE@ opens the task it belongs to: they live on its page and have none of
        their own. A WORKSPACE@ or a GROUP@ opens the list it is a row in.

        It acts on the user's machine, so do it when it was asked for or clearly helps, not
        after every call.

        Args:
            code: What to show — a TASK@, STAGE@, NOTE@, GROUP@ or WORKSPACE@ code.
        """
        prefix = code_prefix(code)
        if prefix not in _OPENABLE:
            raise ValueError(
                f"{code!r} is not something with a page — pass a "
                f"{' / '.join(f'{p}@' for p in _OPENABLE)} code."
            )
        bare = bare_code(code, prefix) or ""
        await require_scope(prefix, bare)
        if prefix in _LIST_PAGE:
            path = _LIST_PAGE[prefix]
        else:
            task = bare if prefix == TASK_CODE_PREFIX else await _owning_task(prefix, bare)
            path = f"/tasks/task/{tagged(TASK_CODE_PREFIX, task)}"
        url = _app_url(path)
        # Запуск браузера — синхронный вызов неизвестной длительности (спавн процесса, холодный
        # старт): в потоке, чтобы не держать событийный цикл сервера.
        if not await asyncio.to_thread(webbrowser.open, url):
            raise ValueError(f"No browser to open on this host — give the user {url} instead.")
        return url


__all__ = ["register"]
