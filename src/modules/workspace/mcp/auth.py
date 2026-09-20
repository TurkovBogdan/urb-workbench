"""Резолвер MCP-токена — черновой, до появления auth-модуля.

``mount_mcp_servers`` собирает с модулей **ровно один** ``mcp_token_resolver`` и строит из него
общий верификатор на все смонтированные серверы. Поставщик обязан быть, и обязан быть один: ни
одного — монтаж отказывает, двое — тоже.

**Почему это здесь.** Не потому, что авторизация — дело пространства, а потому, что ``workspace``
стоит на уровне 1: он ниже всех прикладных модулей и переживёт любой из них. Раньше резолвер
держал ``research`` — эталонный модуль, который по замыслу однажды удаляют, и удаление уронило
бы MCP целиком, включая чужие серверы. Зависимость от того, что кто-то сверху не исчезнет, —
это не зависимость, а отложенная поломка.

Проверка простая: предъявленный bearer сверяется со статичным токеном из ENV
(``Config.mcp_token``). Пусто = локальный режим без проверки (allow-all, dev). Будущий
auth-модуль заберёт эту роль вместе с выдачей токенов, и тогда объявление уедет к нему — но
уедет из места, которое не собирались сносить.

``fastmcp`` не тянет: только ``Config`` и dataclass. Тип принципала утиный (``id``/``group``),
как ждёт ``McpServerTokenVerifier``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from src.core.config import Config

if TYPE_CHECKING:
    from src.core.mcp.context import McpPrincipal

_MCP_SCOPE = "mcp"


@dataclass(frozen=True)
class _StaticPrincipal:
    id: int = 0
    group: str = "workspace"


async def resolve_mcp_token(token: str, scope: str) -> "McpPrincipal | None":
    """Bearer → принципал; чужой scope и несовпавший токен — ``None`` (верификатор даст 401)."""
    if scope != _MCP_SCOPE:
        return None
    configured = Config().mcp_token
    if not configured:
        return _StaticPrincipal()
    return _StaticPrincipal() if token == configured else None


__all__ = ["resolve_mcp_token"]
