"""``POST /internal/core/lookup/preview``: the route's own part — the workspace passed on as a
filter, the record shape on the wire, the batch limit — over a fake handler.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from src.core.api import register_exception_handlers
from src.modules.core_lookup.api import router
from src.modules.core_lookup.dto import CODE_MAX, MAX_CODES
from src.modules.core_lookup.registry import LookupType, Miss, Preview, register_type

pytestmark = pytest.mark.pure

URL = "/internal/core/lookup/preview"


@pytest.fixture
async def client():
    app = FastAPI()
    register_exception_handlers(app)
    # The prefix mirrors the production one (``CoreLookupModule.internal_router_prefix``).
    app.include_router(router, prefix="/internal/core/lookup")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


@pytest.fixture
def seen() -> list[dict]:
    calls: list[dict] = []

    async def tasks(codes, filters):
        calls.append(dict(filters))
        return {"AA": Preview("A", "about A", "/tasks/task/TASK@AA"), "BB": Miss.DELETED}

    register_type(LookupType("TASK", tasks))
    return calls


def test_the_route_is_mounted_in_the_assembled_internal_zone():
    from src.apps.app.modules import build_modules
    from src.core.router.internal import build_internal_zone

    paths = {route.path for route in build_internal_zone(build_modules()).routes}

    assert "/core/lookup/preview" in paths


async def test_a_preview_and_an_error_come_back_as_records(client, seen):
    response = await client.post(URL, json={"codes": ["TASK@AA", "TASK@BB"]})

    assert response.status_code == 200
    assert response.json() == [
        {
            "code": "TASK@AA",
            "title": "A",
            "description": "about A",
            "link": "/tasks/task/TASK@AA",
            "error": None,
        },
        {
            "code": "TASK@BB",
            "title": "",
            "description": "",
            "link": "",
            "error": {"code": "deleted", "message": "The entity is deleted."},
        },
    ]


async def test_the_workspace_reaches_the_handler_as_a_filter(client, seen):
    await client.post(URL, json={"codes": ["TASK@AA"], "workspace": "WORKSPACE@CC"})
    await client.post(URL, json={"codes": ["TASK@AA"]})

    assert seen == [{"workspace": "WORKSPACE@CC"}, {}]


async def test_a_batch_over_the_limit_is_refused_whole(client, seen):
    codes = [f"TASK@{n:010X}" for n in range(MAX_CODES + 1)]

    response = await client.post(URL, json={"codes": codes})

    assert response.status_code == 422
    assert seen == []


async def test_a_full_batch_is_answered(client, seen):
    """The boundary itself: the limit is a ceiling, not an off-by-one."""
    codes = [f"TASK@{n:010X}" for n in range(MAX_CODES)]

    response = await client.post(URL, json={"codes": codes})

    assert response.status_code == 200
    assert len(response.json()) == MAX_CODES


async def test_an_overlong_code_is_refused_before_any_handler(client, seen):
    ok = await client.post(URL, json={"codes": ["TASK@" + "A" * (CODE_MAX - 5)]})
    response = await client.post(URL, json={"codes": ["TASK@" + "A" * (CODE_MAX - 4)]})

    assert ok.status_code == 200
    assert response.status_code == 422
    assert seen == [{}], "only the first request reached the handler"


@pytest.mark.parametrize(
    "request_kwargs",
    [
        {},
        {"content": b"{codes:", "headers": {"content-type": "application/json"}},
        {"content": b'{"codes": ["TASK@AA"]}', "headers": {"content-type": "text/plain"}},
        {"json": ["TASK@AA"]},
        {"json": {"codes": "TASK@AA"}},
        {"json": {"codes": None}},
        {"json": {"codes": [None]}},
        {"json": {"codes": [1]}},
        {"json": {"codes": ["TASK@AA"], "workspace": 5}},
    ],
    ids=[
        "no-body",
        "malformed-json",
        "text-plain",
        "array-body",
        "codes-string",
        "codes-null",
        "code-null",
        "code-int",
        "workspace-int",
    ],
)
async def test_a_hostile_body_is_a_clean_json_422(client, seen, request_kwargs):
    response = await client.post(URL, **request_kwargs)

    assert response.status_code == 422
    assert response.headers["content-type"] == "application/json"
    assert response.json()["code"] == "validation_error"
    assert seen == []


@pytest.mark.parametrize(
    "codes", [[], [""], ["   "], ["TASK@AA\x00"], ["../../etc"], ["TASK@ZZ"]], ids=repr
)
async def test_odd_but_well_formed_codes_answer_200_with_a_record_each(client, seen, codes):
    response = await client.post(URL, json={"codes": codes})

    assert response.status_code == 200
    assert len(response.json()) == len({code.strip().upper() for code in codes})
    assert all(record["error"]["code"] == "not_found" for record in response.json())


async def test_an_empty_workspace_narrows_nothing(client, seen):
    await client.post(URL, json={"codes": ["TASK@AA"], "workspace": ""})

    assert seen == [{}]


async def test_only_post_answers(client, seen):
    response = await client.get(URL, params={"codes": "TASK@AA"})

    assert response.status_code == 405
