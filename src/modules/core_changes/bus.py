"""Шина изменений: раздача опубликованного всем, кто сейчас слушает.

Это не очередь, которая хранит: опубликованное сразу раскладывается по буферам подключённых
слушателей и нигде не остаётся. Никто не слушает — событие пропадает, и это правильно: после
переподключения фронт перечитывает то, что у него на экране, а не догоняет пропущенное.

Живёт в памяти процесса. Правки, прошедшие через этот процесс (интерфейс и MCP-агент пишут через
один бэкенд), видны; правки чужого процесса (worker, второй процесс сервера) — нет. Когда это
понадобится, за тот же ``publish`` / ``subscribe`` встанет связь между процессами, а форма события
и фронт не изменятся.

Буфер слушателя ограничен. Вкладка, которая не успевает забирать (фон, медленная сеть), не копит
память бэка: её буфер очищается и в него кладётся одно «перечитай всё» — стоимость отставания —
один лишний запрос, а не устаревший экран.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass

# Сколько сообщений ждёт в буфере одной вкладки. Сообщение — одна транзакция, поэтому сотни
# хватает с запасом: столько коммитов подряд без единого чтения значит, что вкладка не читает.
BUFFER_SIZE = 256


@dataclass(frozen=True)
class Message:
    """Кадр потока: имя события SSE и его данные (уже JSON-строка)."""

    event: str
    data: str


RESYNC = Message(event="resync", data="{}")


class ChangeBus:
    def __init__(self) -> None:
        self._listeners: set[asyncio.Queue[Message]] = set()

    @property
    def listeners(self) -> int:
        return len(self._listeners)

    def publish(self, message: Message) -> None:
        """Разложить сообщение по буферам слушателей. Не ждёт: зовётся из обработчика коммита."""
        for queue in list(self._listeners):
            try:
                queue.put_nowait(message)
            except asyncio.QueueFull:
                _drain(queue)
                queue.put_nowait(RESYNC)

    @asynccontextmanager
    async def subscribe(self) -> AsyncIterator[asyncio.Queue[Message]]:
        queue: asyncio.Queue[Message] = asyncio.Queue(maxsize=BUFFER_SIZE)
        self._listeners.add(queue)
        try:
            yield queue
        finally:
            self._listeners.discard(queue)


def _drain(queue: asyncio.Queue[Message]) -> None:
    while not queue.empty():
        queue.get_nowait()


bus = ChangeBus()

__all__ = ["BUFFER_SIZE", "ChangeBus", "Message", "RESYNC", "bus"]
