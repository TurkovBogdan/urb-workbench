"""``same_origin_only``: a write a page of another site sent is refused before the route runs.

The rule itself (``origin_allowed``) is tabled in ``tests/modules/core_changes/test_stream.py``,
where the feed's handshake uses it; here — the route dependency on a bare app, with and without a
config carrying the Vite dev origins.
"""

from __future__ import annotations

import pytest
from fastapi import Depends, FastAPI
from httpx import ASGITransport, AsyncClient

from src.core.api import register_exception_handlers
from src.core.config import Config
from src.core.router.origin import same_origin_only

pytestmark = pytest.mark.pure


def _app(config: Config | None = None) -> tuple[FastAPI, list[str]]:
    app = FastAPI()
    register_exception_handlers(app)
    if config is not None:
        app.state.config = config
    calls: list[str] = []

    @app.post("/write", dependencies=[Depends(same_origin_only)])
    async def write() -> dict[str, bool]:
        calls.append("ran")
        return {"ok": True}

    return app, calls


async def _post(app: FastAPI, headers: dict[str, str]):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://127.0.0.1:22140") as client:
        return await client.post("/write", content=b"x", headers=headers)


@pytest.mark.parametrize(
    "headers",
    [{}, {"Origin": "http://127.0.0.1:22140"}],
    ids=["no-origin", "own-origin"],
)
async def test_the_app_s_own_page_and_a_program_pass(headers):
    app, calls = _app()

    response = await _post(app, headers)

    assert response.status_code == 200
    assert calls == ["ran"]


async def test_a_page_of_another_site_is_refused_and_the_route_does_not_run():
    app, calls = _app()

    response = await _post(app, {"Origin": "https://evil.example", "Content-Type": "text/plain"})

    assert response.status_code == 403
    assert response.json()["code"] == "origin_refused"
    assert calls == []


async def test_the_vite_dev_origin_passes_only_with_a_config_naming_it():
    with_config, ran = _app(Config(server_vite_port=22141))
    bare, not_ran = _app()
    vite = {"Origin": "http://localhost:22141"}

    assert (await _post(with_config, vite)).status_code == 200
    assert (await _post(bare, vite)).status_code == 403
    assert (ran, not_ran) == (["ran"], [])
