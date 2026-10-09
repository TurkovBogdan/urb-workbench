"""The changes bus: fans out whatever is published to everyone listening right now.

It is not a queue that stores: a published message is immediately spread across the buffers of
connected listeners and is kept nowhere. If nobody is listening the event is lost, and that is
correct: after reconnecting, the frontend re-reads what it has on screen rather than catching
up on what it missed.

Lives in process memory. Edits that went through this process (the interface and the MCP agent
write through one backend) are visible; edits from another process (the worker, a second server
process) are not. When that becomes necessary, inter-process transport will sit behind the same
``publish`` / ``subscribe``, and neither the event shape nor the frontend will change.

A listener's buffer is bounded. A tab that cannot keep up (background, slow network) does not
pile up backend memory: its buffer is cleared and a single "re-read everything" is put in — the
cost of falling behind is one extra request, not a stale screen.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass

# How many messages wait in one tab's buffer. A message is one transaction, so a few hundred is
# ample: that many commits in a row without a single read means the tab is not reading.
BUFFER_SIZE = 256


@dataclass(frozen=True)
class Message:
    """A feed frame: the event name and its data (already a JSON string)."""

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
        """Spread a message across the listeners' buffers. Never waits: called from a commit hook."""
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
