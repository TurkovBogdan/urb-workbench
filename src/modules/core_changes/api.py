"""The changes feed for the frontend: a WebSocket at ``/internal/core/changes/ws``.

WebSocket, not SSE: a browser keeps at most six HTTP/1.1 connections per origin, and an SSE
stream holds one of them for as long as the tab is open — four tabs left two slots for every
request of every tab, and the interface stalled. A WebSocket does not count against that pool.

The channel is one-way: the backend talks, the tab listens. Whatever the tab sends is read and
dropped — the read is there to notice that the tab is gone.

Frames are JSON objects named by ``event``:

- ``hello`` — the first frame, ``{"event": "hello", "ping": <seconds>}``: the tab arms its
  watchdog by that interval;
- ``changes`` — a transaction's message under ``data``:
  ``{"origin": "<tab id>" | null, "changes": [{"entity", "event", "ids", "refs"}, …]}``.
  ``origin`` is the tab that made the edit (``origin.py``): it lets a tab recognise the echo of
  its own saves. An empty ``ids`` is a bulk operation with no named codes: the listener
  re-reads everything it holds;
- ``resync`` — the tab fell behind and its buffer was dropped: re-read everything on screen;
- ``ping`` — every ``PING_SECONDS`` of quiet, so that a dead link (a laptop back from sleep, a
  backend gone without a close) is noticed by the tab rather than waited on.

What was missed during a drop is not re-sent: the bus stores nothing (``bus.py``). The frontend
treats the reconnect itself as "re-read".

The handshake checks ``Origin``. CORS does not cover WebSocket, so without the check any page
open in the same browser could connect and read the feed. Allowed are the backend's own origin
and the dev origins of ``cors_origins``; a client that sends no ``Origin`` is not a browser and
is let through.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from contextlib import aclosing
from urllib.parse import urlsplit

from fastapi import APIRouter, WebSocket

from src.modules.core_changes.bus import Message, bus

PING_SECONDS = 15

# The WebSocket close code for a refused policy check (RFC 6455).
POLICY_VIOLATION = 1008

router = APIRouter()


def _frame(message: Message) -> str:
    # ``data`` is already JSON, serialized once at publish for every listener.
    return f'{{"event": "{message.event}", "data": {message.data}}}'


async def _frames() -> AsyncIterator[str]:
    async with bus.subscribe() as queue:
        yield json.dumps({"event": "hello", "ping": PING_SECONDS})
        while True:
            try:
                message = await asyncio.wait_for(queue.get(), timeout=PING_SECONDS)
            except TimeoutError:
                yield json.dumps({"event": "ping"})
                continue
            yield _frame(message)


def origin_allowed(origin: str | None, host: str | None, dev_origins: list[str]) -> bool:
    if origin is None:
        return True
    return urlsplit(origin).netloc == host or origin in dev_origins


async def _send(websocket: WebSocket) -> None:
    async with aclosing(_frames()) as frames:
        async for frame in frames:
            await websocket.send_text(frame)


async def _until_closed(websocket: WebSocket) -> None:
    while (await websocket.receive())["type"] != "websocket.disconnect":
        pass


@router.websocket("/ws")
async def feed(websocket: WebSocket) -> None:
    headers = websocket.headers
    dev_origins = websocket.app.state.config.cors_origins
    if not origin_allowed(headers.get("origin"), headers.get("host"), dev_origins):
        await websocket.close(code=POLICY_VIOLATION)
        return
    await websocket.accept()
    sending = asyncio.create_task(_send(websocket))
    listening = asyncio.create_task(_until_closed(websocket))
    try:
        await asyncio.wait({sending, listening}, return_when=asyncio.FIRST_COMPLETED)
    finally:
        for task in (sending, listening):
            task.cancel()
        # A send into a socket the tab has just closed fails; the tab is gone either way.
        await asyncio.gather(sending, listening, return_exceptions=True)


__all__ = ["PING_SECONDS", "POLICY_VIOLATION", "origin_allowed", "router"]
