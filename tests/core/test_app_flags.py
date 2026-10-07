"""`/internal/core/app`: the SPA learns the process switches from the config it started with."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from src.core.app_factory import create_app
from src.core.config import Config

pytestmark = pytest.mark.pure


@pytest.mark.parametrize("dev_mode", [False, True])
async def test_dev_mode_is_served_as_the_process_started_with_it(dev_mode: bool):
    app = create_app([], Config(app_dev_mode=dev_mode))

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/internal/core/app")

    assert response.status_code == 200
    assert response.json() == {"dev_mode": dev_mode}


def test_dev_mode_is_off_unless_set(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("APP_DEV_MODE", raising=False)

    assert Config(_env_file=None).app_dev_mode is False
