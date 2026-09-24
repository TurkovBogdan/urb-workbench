"""Источник правки: какая вкладка интерфейса её сделала.

Вкладка шлёт свой случайный id в заголовке ``X-Client-Id`` каждого запроса. Прослойка кладёт его
в переменную контекста на время запроса, сборщик изменений при сбросе в базу читает её и ставит
в сообщение ленты как ``origin``. По нему вкладка узнаёт эхо собственных сохранений и не
перечитывает то, что сама только что записала.

Без заголовка — MCP-агент, фоновые задачи, другие клиенты — ``origin`` пустой, то есть «не вы» для
любой вкладки.

Прослойка — чистый ASGI, а не ``BaseHTTPMiddleware``: переменная ставится в той же задаче, в
которой выполняется обработчик запроса, и точно видна из обработчиков событий сессии SQLAlchemy.
"""

from __future__ import annotations

from contextvars import ContextVar

CLIENT_ID_HEADER = "x-client-id"

# Потолок длины: заголовок приходит снаружи, и строка неограниченной длины поехала бы в каждое
# сообщение ленты каждой вкладке.
_MAX_LEN = 64

current_origin: ContextVar[str | None] = ContextVar("core_changes_origin", default=None)


class OriginMiddleware:
    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        origin = None
        for name, value in scope.get("headers", ()):
            if name == CLIENT_ID_HEADER.encode():
                origin = value.decode("latin-1")[:_MAX_LEN] or None
                break
        token = current_origin.set(origin)
        try:
            await self.app(scope, receive, send)
        finally:
            current_origin.reset(token)


__all__ = ["CLIENT_ID_HEADER", "OriginMiddleware", "current_origin"]
