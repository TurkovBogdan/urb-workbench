"""Кадры SSE-потока и поведение шины: приветствие, событие, отставший слушатель."""

from __future__ import annotations

import asyncio

import pytest

from src.modules.core_changes import api
from src.modules.core_changes.bus import BUFFER_SIZE, RESYNC, ChangeBus, Message, bus

pytestmark = pytest.mark.pure


async def test_stream_greets_then_relays_published_frames():
    frames = api._frames()
    greeting = await anext(frames)
    assert greeting.startswith(f"retry: {api.RETRY_MS}\n")
    assert bus.listeners == 1

    bus.publish(Message(event="changes", data='{"changes": []}'))
    assert await anext(frames) == 'event: changes\ndata: {"changes": []}\n\n'

    await frames.aclose()
    assert bus.listeners == 0


async def test_idle_stream_sends_ping(monkeypatch):
    monkeypatch.setattr(api, "PING_SECONDS", 0.01)
    frames = api._frames()
    await anext(frames)
    assert await anext(frames) == ": ping\n\n"
    await frames.aclose()


async def test_lagging_listener_gets_one_resync_instead_of_a_backlog():
    local = ChangeBus()
    async with local.subscribe() as queue:
        for n in range(BUFFER_SIZE + 5):
            local.publish(Message(event="changes", data=str(n)))
        received = []
        while not queue.empty():
            received.append(queue.get_nowait())
    assert RESYNC in received
    assert len(received) < BUFFER_SIZE


async def test_publish_without_listeners_is_a_no_op():
    ChangeBus().publish(Message(event="changes", data="{}"))
    await asyncio.sleep(0)
