"""An upload request under concurrent PUTs, on PostgreSQL — where the claims really overlap.

SQLite takes one writer at a time (``BEGIN IMMEDIATE``); PostgreSQL runs the claims side by side,
and the one-statement claim (``UPDATE … WHERE claimed_at IS NULL``) is what lets exactly one of
them through: the row's lock queues the others, and they find the request taken. Each scenario
runs many rounds: one interleaving that binds twice is enough to fail.
"""

from __future__ import annotations

import asyncio

import pytest

from src.core.database import get_engine
from src.modules.core_storage_upload.errors import RequestNotFound
from src.modules.core_storage_upload.services.requests import (
    open_upload_request,
    upload_with_request,
)

pytestmark = pytest.mark.heavy

ROUNDS = 20


async def _chunks(data: bytes):
    yield data


async def test_this_tier_really_runs_on_postgres(db):
    assert get_engine().dialect.name == "postgresql"


async def test_concurrent_puts_on_one_request_bind_once(db, holder):
    from urllib.parse import parse_qs, urlsplit

    bound = []
    for n in range(ROUNDS):
        address = await open_upload_request("TEST@1", workspace="WS1", payload={"title": f"{n}"})
        token = parse_qs(urlsplit(address.path).query)["token"][0]
        before = len(holder.attached)

        results = await asyncio.gather(
            *(upload_with_request(token, _chunks(f"{n}-{k}".encode())) for k in range(4)),
            return_exceptions=True,
        )

        done = [result for result in results if not isinstance(result, BaseException)]
        refused = [result for result in results if isinstance(result, BaseException)]
        assert all(isinstance(error, RequestNotFound) for error in refused), refused
        bound.append((len(done), len(holder.attached) - before))
    assert set(bound) == {(1, 1)}
