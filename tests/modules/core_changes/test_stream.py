"""Feed socket frames, the handshake's origin check, and bus behaviour."""

from __future__ import annotations

import asyncio
import json

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from src.core.app_factory import create_app
from src.core.config import Config
from src.modules.core_changes import CoreChangesModule, api
from src.modules.core_changes.bus import BUFFER_SIZE, RESYNC, ChangeBus, Message, bus

pytestmark = pytest.mark.pure

_FEED = "/internal/core/changes/ws"
_DEV_ORIGINS = ["http://localhost:5173"]


async def test_feed_greets_then_relays_published_frames():
    frames = api._frames()
    assert json.loads(await anext(frames)) == {"event": "hello", "ping": api.PING_SECONDS}
    assert bus.listeners == 1

    bus.publish(Message(event="changes", data='{"changes": []}'))
    assert json.loads(await anext(frames)) == {"event": "changes", "data": {"changes": []}}

    await frames.aclose()
    assert bus.listeners == 0


async def test_idle_feed_sends_ping(monkeypatch):
    monkeypatch.setattr(api, "PING_SECONDS", 0.01)
    frames = api._frames()
    await anext(frames)
    assert json.loads(await anext(frames)) == {"event": "ping"}
    await frames.aclose()


def test_resync_frame_is_valid_json():
    assert json.loads(api._frame(RESYNC)) == {"event": "resync", "data": {}}


@pytest.mark.parametrize(
    ("origin", "allowed"),
    [
        (None, True),
        ("http://127.0.0.1:22140", True),
        ("http://localhost:5173", True),
        ("https://evil.example", False),
        ("http://127.0.0.1:9999", False),
        # Sandboxed frames and file:// pages send the literal ``null``.
        ("null", False),
    ],
)
def test_origin_check(origin: str | None, allowed: bool):
    assert api.origin_allowed(origin, "127.0.0.1:22140", _DEV_ORIGINS) is allowed


async def _publish(message: Message) -> None:
    bus.publish(message)


def _app(config: Config | None = None) -> FastAPI:
    app = FastAPI()
    app.state.config = config or Config()
    app.include_router(api.router, prefix="/internal/core/changes")
    return app


def _hello(socket) -> None:
    assert socket.receive_json() == {"event": "hello", "ping": api.PING_SECONDS}


def test_socket_relays_a_published_change_and_leaves_the_bus_on_close():
    with TestClient(_app()).websocket_connect(_FEED) as socket:
        _hello(socket)
        # Published on the app's loop: the listener's queue belongs to it, not to this thread.
        message = Message(event="changes", data='{"origin": null, "changes": []}')
        socket.portal.call(_publish, message)
        assert socket.receive_json() == {
            "event": "changes",
            "data": {"origin": None, "changes": []},
        }
    assert bus.listeners == 0


async def test_handler_ends_on_its_own_when_the_tab_leaves(monkeypatch):
    """Driven bare, the way uvicorn drives it: a tab leaving is a ``websocket.disconnect`` in the
    inbox, never a cancelled task. ``TestClient`` cancels the app on exit and would hide a handler
    that only notices the loss on its next send — up to a ping interval later."""
    monkeypatch.setattr(api, "PING_SECONDS", 3600)
    inbox: asyncio.Queue[dict] = asyncio.Queue()
    inbox.put_nowait({"type": "websocket.connect"})

    async def receive() -> dict:
        return await inbox.get()

    async def send(message: dict) -> None:
        if message["type"] == "websocket.send":
            inbox.put_nowait({"type": "websocket.disconnect", "code": 1001})

    scope = {
        "type": "websocket",
        "asgi": {"version": "3.0"},
        "scheme": "ws",
        "path": _FEED,
        "raw_path": _FEED.encode(),
        "root_path": "",
        "query_string": b"",
        "headers": [],
        "client": ("127.0.0.1", 50000),
        "server": ("testserver", 80),
        "subprotocols": [],
    }
    await asyncio.wait_for(_app()(scope, receive, send), timeout=2)
    assert bus.listeners == 0


def test_socket_relays_resync():
    with TestClient(_app()).websocket_connect(_FEED) as socket:
        _hello(socket)
        socket.portal.call(_publish, RESYNC)
        assert socket.receive_json() == {"event": "resync", "data": {}}


def test_idle_socket_sends_ping(monkeypatch):
    monkeypatch.setattr(api, "PING_SECONDS", 0.05)
    with TestClient(_app()).websocket_connect(_FEED) as socket:
        socket.receive_json()
        assert socket.receive_json() == {"event": "ping"}


@pytest.mark.parametrize(
    "origin",
    [
        # The backend serving the SPA itself: TestClient's Host is ``testserver``.
        "http://testserver",
        # The Vite dev server, a different port of the same machine.
        "http://localhost:22141",
    ],
)
def test_socket_from_an_allowed_origin_is_accepted(origin: str):
    client = TestClient(_app(Config(server_vite_port=22141)))
    with client.websocket_connect(_FEED, headers={"origin": origin}) as socket:
        _hello(socket)


def test_socket_from_a_foreign_origin_is_refused():
    client = TestClient(_app())
    with pytest.raises(WebSocketDisconnect) as refused:
        with client.websocket_connect(_FEED, headers={"origin": "https://evil.example"}):
            pass
    # The number, not the constant: the code is a contract with the browser (RFC 6455).
    assert refused.value.code == 1008
    assert bus.listeners == 0


def test_socket_is_served_by_the_assembled_app():
    """Through everything a real request crosses: the gate, the SPA, the origin tag, the zone guard."""
    app = create_app(modules=[CoreChangesModule()], config=Config(server_enabled=True))
    with TestClient(app).websocket_connect(_FEED) as socket:
        _hello(socket)
        socket.portal.call(_publish, RESYNC)
        assert socket.receive_json()["event"] == "resync"
    assert bus.listeners == 0


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
