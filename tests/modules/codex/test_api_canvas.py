"""What the interface reads besides the rows: how widely a codex is mounted, and the canvas tree."""

from __future__ import annotations

import pytest

from src.modules.workspace.crud.workspace import workspace_create, workspace_delete

pytestmark = pytest.mark.db

API = "/internal/codex"


async def _codex(client, segment):
    return (await client.post(f"{API}/codexes", json={"segment": segment, "title": segment})).json()["code"]


async def test_the_mount_count_follows_live_workspaces(client, workspace):
    python = await _codex(client, "python")
    other = await workspace_create(title="Личное")
    gone = await workspace_create(title="Архив")
    for ws in (workspace, other, gone):
        await client.post(f"{API}/workspaces/WORKSPACE@{ws.code}/mounts", json={"codex_code": python})
    await workspace_delete(gone.code)

    listed = (await client.get(f"{API}/codexes")).json()
    assert [(c["segment"], c["mount_count"]) for c in listed] == [("python", 2)]
    assert (await client.get(f"{API}/codexes/{python}")).json()["mount_count"] == 2
    canvas = (await client.get(f"{API}/workspaces/WORKSPACE@{workspace.code}/mounts")).json()
    assert canvas[0]["codex"]["mount_count"] == 2


async def test_the_trash_lists_each_deletion_once_by_its_root(client):
    python = await _codex(client, "python")

    async def note(parent, segment):
        body = {"parent_code": parent, "segment": segment, "title": segment}
        return (await client.post(f"{API}/notes", json=body)).json()["code"]

    test = await note(python, "test")
    await note(test, "fixtures")
    lint = await note(python, "lint")
    await client.delete(f"{API}/notes/{test}?branch=true")
    await client.delete(f"{API}/notes/{lint}")

    trash = (await client.get(f"{API}/codexes/{python}/trash")).json()
    assert sorted(row["segment"] for row in trash) == ["lint", "test"]

    await client.post(f"{API}/notes/{test}/restore")
    assert [row["segment"] for row in (await client.get(f"{API}/codexes/{python}/trash")).json()] == [
        "lint"
    ]
    assert (await client.get(f"{API}/codexes/CODEX@0000000000/trash")).status_code == 404


async def test_the_canvas_tree_holds_only_mounted_codexes(client, workspace):
    python = await _codex(client, "python")
    await _codex(client, "sql")
    test = (
        await client.post(
            f"{API}/notes", json={"parent_code": python, "segment": "test", "title": "Тесты"}
        )
    ).json()["code"]
    ws = f"WORKSPACE@{workspace.code}"
    assert (await client.get(f"{API}/workspaces/{ws}/tree")).json() == []

    await client.post(f"{API}/workspaces/{ws}/mounts", json={"codex_code": python})
    tree = (await client.get(f"{API}/workspaces/{ws}/tree")).json()
    assert [n["path"] for n in tree] == ["python"]
    assert [(c["code"], c["path"]) for c in tree[0]["children"]] == [(test, "python/test")]
    assert (await client.get(f"{API}/workspaces/WORKSPACE@0000000000/tree")).status_code == 404


async def test_the_canvas_tree_shows_deleted_notes_only_when_asked(client, workspace):
    python = await _codex(client, "python")
    ws = f"WORKSPACE@{workspace.code}"
    await client.post(f"{API}/workspaces/{ws}/mounts", json={"codex_code": python})

    async def note(parent, segment):
        body = {"parent_code": parent, "segment": segment, "title": segment}
        return (await client.post(f"{API}/notes", json=body)).json()["code"]

    test = await note(python, "test")
    fixtures = await note(test, "fixtures")
    await note(python, "lint")
    await client.delete(f"{API}/notes/{test}?branch=true")

    live = (await client.get(f"{API}/workspaces/{ws}/tree")).json()
    assert [c["segment"] for c in live[0]["children"]] == ["lint"]
    assert live[0]["deleted"] is False

    whole = (await client.get(f"{API}/workspaces/{ws}/tree?include_deleted=true")).json()
    by_segment = {c["segment"]: c for c in whole[0]["children"]}
    assert (by_segment["test"]["deleted"], by_segment["lint"]["deleted"]) == (True, False)
    assert [(c["code"], c["deleted"]) for c in by_segment["test"]["children"]] == [(fixtures, True)]


async def test_the_canvas_search_finds_records_by_their_contents(client, workspace):
    python = await _codex(client, "python")
    await _codex(client, "sql")
    ws = f"WORKSPACE@{workspace.code}"
    await client.post(f"{API}/workspaces/{ws}/mounts", json={"codex_code": python})
    body = {"parent_code": python, "segment": "test", "title": "Тесты", "body": "Фабрики в CONFTEST"}
    test = (await client.post(f"{API}/notes", json=body)).json()["code"]
    lint = {"parent_code": python, "segment": "lint", "title": "Линтер", "description": "ruff"}
    await client.post(f"{API}/notes", json=lint)

    assert (await client.get(f"{API}/workspaces/{ws}/search", params={"query": "conftest"})).json() == [test]
    assert (await client.get(f"{API}/workspaces/{ws}/search", params={"query": "ФАБРИК"})).json() == [test]
    assert (await client.get(f"{API}/workspaces/{ws}/search", params={"query": "  "})).json() == []
    assert (await client.get(f"{API}/workspaces/WORKSPACE@0000000000/search", params={"query": "x"})).status_code == 404
