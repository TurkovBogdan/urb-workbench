"""Поток изменений для фронта: ``GET /internal/core/changes/stream``, Server-Sent Events.

SSE, а не WebSocket: связь нужна в одну сторону, а браузерный ``EventSource`` сам переподключается
после обрыва. Это обычный HTTP-ответ, который не кончается, — та же зона, те же guard'ы, тот же
прокси Vite в dev, без новых зависимостей.

Кадры:

- ``changes`` — сообщение транзакции:
  ``{"origin": "<id вкладки>" | null, "changes": [{"entity", "event", "ids", "refs"}, …]}``.
  ``origin`` — вкладка, сделавшая правку (``origin.py``): по нему вкладка узнаёт эхо своих
  сохранений. Пустой ``ids`` — массовая операция без названных кодов: слушатель перечитывает
  всё своё;
- ``resync`` — вкладка отстала и её буфер сброшен: перечитать всё, что на экране;
- комментарий ``: ping`` — раз в ``PING_SECONDS``, чтобы простаивающее соединение не закрыл
  кто-нибудь по дороге и чтобы разрыв замечался, а не висел.

Пропущенное за время обрыва не досылается: шина ничего не хранит (``bus.py``). Первый кадр
``retry`` задаёт паузу переподключения, а сам факт переподключения фронт понимает как «перечитай».
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from src.modules.core_changes.bus import Message, bus

PING_SECONDS = 15
RETRY_MS = 2000

router = APIRouter()


def _frame(message: Message) -> str:
    return f"event: {message.event}\ndata: {message.data}\n\n"


async def _frames() -> AsyncIterator[str]:
    async with bus.subscribe() as queue:
        yield f"retry: {RETRY_MS}\n: connected\n\n"
        while True:
            try:
                message = await asyncio.wait_for(queue.get(), timeout=PING_SECONDS)
            except TimeoutError:
                yield ": ping\n\n"
                continue
            yield _frame(message)


@router.get("/stream")
async def stream() -> StreamingResponse:
    # ``X-Accel-Buffering: no`` — на случай прокси перед бэком: буферизованный поток доходил бы
    # пачками раз в несколько секунд, то есть переставал бы быть живым.
    return StreamingResponse(
        _frames(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


__all__ = ["PING_SECONDS", "RETRY_MS", "router"]
