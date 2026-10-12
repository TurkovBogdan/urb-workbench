"""The person's HTTP API over codexes, notes and mounts: each route's success and its own refusal,
and the data read back after a refusal.

The rules themselves are the service's and are tested there; here is what the route adds — the
status, the code the interface translates, and that a refused call wrote nothing.
"""

from __future__ import annotations

import pytest

from src.modules.workspace.crud.workspace import workspace_delete

pytestmark = pytest.mark.db

API = "/internal/codex"


async def _codex(client, segment="python", **extra):
    response = await client.post(f"{API}/codexes", json={"segment": segment, "title": segment, **extra})
    assert response.status_code == 201, response.text
    return response.json()


async def _note(client, parent, segment, **extra):
    response = await client.post(
        f"{API}/notes", json={"parent_code": parent, "segment": segment, "title": segment, **extra}
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_the_routes_are_mounted_in_the_assembled_internal_zone():
    from src.apps.app.modules import build_modules
    from src.core.router.internal import build_internal_zone

    paths = {route.path for route in build_internal_zone(build_modules()).routes}

    assert {
        "/codex/codexes",
        "/codex/codexes/{code}/tree",
        "/codex/notes/{code}/move",
        "/codex/workspaces/{workspace}/mounts",
    } <= paths


# ── codexes ───────────────────────────────────────────────────────────────────


async def test_a_codex_is_created_read_and_listed_with_its_prefix(client):
    created = await _codex(client, body="Правила")

    assert created["code"].startswith("CODEX@")
    got = (await client.get(f"{API}/codexes/{created['code'].lower()}")).json()
    assert (got["segment"], got["body"]) == ("python", "Правила")
    listed = (await client.get(f"{API}/codexes")).json()
    assert [c["segment"] for c in listed] == ["python"]
    assert "body" not in listed[0]


async def test_a_taken_segment_is_409_and_writes_nothing(client):
    await _codex(client)

    response = await client.post(f"{API}/codexes", json={"segment": "python", "title": "Ещё"})
    assert response.status_code == 409
    assert "taken by the codex" in response.json()["error"]
    assert len((await client.get(f"{API}/codexes")).json()) == 1


async def test_an_unknown_field_is_refused(client):
    response = await client.post(f"{API}/codexes", json={"segment": "a", "title": "A", "name": "x"})

    assert response.status_code == 422
    assert (await client.get(f"{API}/codexes")).json() == []


async def test_a_foreign_code_is_400_and_a_missing_one_404(client):
    foreign = await client.get(f"{API}/codexes/TASK@0000000000")
    missing = await client.get(f"{API}/codexes/CODEX@0000000000")

    assert foreign.status_code == 400
    assert (missing.status_code, missing.json()["code"]) == (404, "codex.codex.not_found")


async def test_a_codex_is_updated_whole(client):
    code = (await _codex(client))["code"]

    response = await client.put(
        f"{API}/codexes/{code}", json={"segment": "py", "title": "Python", "body": "Новые"}
    )
    assert response.status_code == 200
    assert (response.json()["segment"], response.json()["description"]) == ("py", "")


async def test_the_look_is_kept_by_a_save_that_does_not_carry_it(client):
    created = await client.post(
        f"{API}/codexes", json={"segment": "python", "title": "Python", "color": "teal", "icon": "brand-python"}
    )
    code = created.json()["code"]
    assert (created.json()["color"], created.json()["icon"]) == ("teal", "brand-python")

    text_only = await client.put(f"{API}/codexes/{code}", json={"segment": "python", "title": "Python", "body": "Правила"})
    assert (text_only.json()["color"], text_only.json()["icon"]) == ("teal", "brand-python")

    cleared = await client.put(
        f"{API}/codexes/{code}", json={"segment": "python", "title": "Python", "color": "", "icon": ""}
    )
    assert (cleared.json()["color"], cleared.json()["icon"]) == ("", "")


async def test_a_deleted_codex_takes_no_edits_and_comes_back(client):
    code = (await _codex(client))["code"]

    assert (await client.delete(f"{API}/codexes/{code}")).status_code == 204
    put = await client.put(f"{API}/codexes/{code}", json={"segment": "python", "title": "X"})
    assert (put.status_code, put.json()["code"]) == (409, "codex.codex.deleted")
    assert (await client.get(f"{API}/codexes/{code}")).json()["title"] == "python"

    restored = await client.post(f"{API}/codexes/{code}/restore")
    assert (restored.status_code, restored.json()["deleted_at"]) == (200, None)
    again = await client.post(f"{API}/codexes/{code}/restore")
    assert (again.status_code, again.json()["code"]) == (409, "codex.codex.not_deleted")


async def test_a_restore_refused_by_a_taken_segment_is_409(client):
    old = (await _codex(client))["code"]
    await client.delete(f"{API}/codexes/{old}")
    await _codex(client)

    response = await client.post(f"{API}/codexes/{old}/restore")
    assert response.status_code == 409
    assert (await client.get(f"{API}/codexes/{old}")).json()["deleted_at"] is not None


async def test_the_tree_of_a_codex(client):
    codex = (await _codex(client))["code"]
    test = (await _note(client, codex, "test"))["code"]
    await _note(client, test, "fixtures")

    tree = (await client.get(f"{API}/codexes/{codex}/tree")).json()
    assert tree["path"] == "python"
    assert [c["path"] for c in tree["children"]] == ["python/test"]
    assert [c["path"] for c in tree["children"][0]["children"]] == ["python/test/fixtures"]
    assert (await client.get(f"{API}/codexes/CODEX@0000000000/tree")).status_code == 404


# ── notes ─────────────────────────────────────────────────────────────────────


async def test_a_note_carries_its_place(client):
    codex = (await _codex(client))["code"]
    test = await _note(client, codex, "test")
    fixtures = await _note(client, test["code"], "fixtures", body="Текст")

    assert (test["parent_code"], test["path"]) == (None, "python/test")
    got = (await client.get(f"{API}/notes/{fixtures['code']}")).json()
    assert (got["codex_code"], got["parent_code"]) == (codex, test["code"])
    assert (got["path"], got["body"]) == ("python/test/fixtures", "Текст")


async def test_a_rule_refusal_is_409_with_the_service_text(client):
    codex = (await _codex(client))["code"]
    await _note(client, codex, "test")

    response = await client.post(
        f"{API}/notes", json={"parent_code": codex, "segment": "test", "title": "Ещё"}
    )
    assert response.status_code == 409
    assert "taken under the codex 'python'" in response.json()["error"]
    assert len((await client.get(f"{API}/codexes/{codex}/tree")).json()["children"]) == 1


async def test_a_note_is_updated_whole_and_a_deleted_one_refuses(client):
    codex = (await _codex(client))["code"]
    code = (await _note(client, codex, "test"))["code"]

    put = await client.put(f"{API}/notes/{code}", json={"segment": "tests", "title": "Тесты"})
    assert (put.status_code, put.json()["path"]) == (200, "python/tests")

    await client.delete(f"{API}/notes/{code}")
    refused = await client.put(f"{API}/notes/{code}", json={"segment": "x", "title": "X"})
    assert (refused.status_code, refused.json()["code"]) == (409, "codex.note.deleted")
    got = (await client.get(f"{API}/notes/{code}")).json()
    assert (got["segment"], got["path"]) == ("tests", "")


async def test_move_and_place(client):
    codex = (await _codex(client))["code"]
    test = (await _note(client, codex, "test"))["code"]
    lint = (await _note(client, codex, "lint"))["code"]
    fixtures = (await _note(client, test, "fixtures"))["code"]

    moved = await client.post(f"{API}/notes/{fixtures}/move", json={"parent_code": lint})
    assert (moved.status_code, moved.json()["path"]) == (200, "python/lint/fixtures")

    await client.post(f"{API}/notes/{lint}/move", json={"after_code": None})
    tree = (await client.get(f"{API}/codexes/{codex}/tree")).json()
    assert [c["segment"] for c in tree["children"]] == ["lint", "test"]

    loop = await client.post(f"{API}/notes/{lint}/move", json={"parent_code": fixtures})
    assert loop.status_code == 409
    assert (await client.get(f"{API}/notes/{lint}")).json()["parent_code"] is None


async def test_a_move_without_after_keeps_the_place(client):
    codex = (await _codex(client))["code"]
    await _note(client, codex, "test")
    lint = (await _note(client, codex, "lint"))["code"]
    await client.post(f"{API}/notes/{lint}/move", json={"after_code": None})

    await client.post(f"{API}/notes/{lint}/move", json={})
    tree = (await client.get(f"{API}/codexes/{codex}/tree")).json()
    assert [c["segment"] for c in tree["children"]] == ["lint", "test"]


async def test_a_note_with_children_is_409_naming_them_and_goes_with_its_branch(client):
    codex = (await _codex(client))["code"]
    test = (await _note(client, codex, "test"))["code"]
    await _note(client, test, "fixtures")

    refused = await client.delete(f"{API}/notes/{test}")
    body = refused.json()
    assert (refused.status_code, body["code"]) == (409, "codex.note.has_children")
    assert body["params"] == {"count": 1, "children": "fixtures"}
    assert (await client.get(f"{API}/notes/{test}")).json()["deleted_at"] is None

    assert (await client.delete(f"{API}/notes/{test}?branch=true")).status_code == 204
    assert (await client.get(f"{API}/codexes/{codex}/tree")).json()["children"] == []

    restored = await client.post(f"{API}/notes/{test}/restore")
    assert (restored.status_code, restored.json()["path"]) == (200, "python/test")
    again = await client.post(f"{API}/notes/{test}/restore")
    assert (again.status_code, again.json()["code"]) == (409, "codex.note.not_deleted")


async def test_a_missing_note_is_404(client):
    for response in (
        await client.get(f"{API}/notes/CODEX@0000000000"),
        await client.delete(f"{API}/notes/CODEX@0000000000"),
    ):
        assert (response.status_code, response.json()["code"]) == (404, "codex.note.not_found")


# ── mounts ────────────────────────────────────────────────────────────────────


async def test_mounting_and_the_canvas(client, workspace):
    python = (await _codex(client))["code"]
    vue = (await _codex(client, "vue"))["code"]
    ws = f"WORKSPACE@{workspace.code}"

    first = await client.post(f"{API}/workspaces/{ws}/mounts", json={"codex_code": python})
    assert first.status_code == 201
    assert (first.json()["codex"]["segment"], first.json()["agent_can_edit"]) == ("python", True)
    await client.post(
        f"{API}/workspaces/{ws}/mounts", json={"codex_code": vue, "agent_can_edit": False}
    )

    canvas = (await client.get(f"{API}/workspaces/{ws}/mounts")).json()
    assert [(m["codex"]["segment"], m["agent_can_edit"]) for m in canvas] == [
        ("python", True),
        ("vue", False),
    ]


async def test_mounting_twice_is_409(client, workspace):
    python = (await _codex(client))["code"]
    ws = f"WORKSPACE@{workspace.code}"
    await client.post(f"{API}/workspaces/{ws}/mounts", json={"codex_code": python})

    response = await client.post(f"{API}/workspaces/{ws}/mounts", json={"codex_code": python})
    assert response.status_code == 409
    assert len((await client.get(f"{API}/workspaces/{ws}/mounts")).json()) == 1


async def test_a_missing_workspace_or_codex_is_404(client, workspace):
    python = (await _codex(client))["code"]
    await workspace_delete(workspace.code)
    ws = f"WORKSPACE@{workspace.code}"

    gone = await client.post(f"{API}/workspaces/{ws}/mounts", json={"codex_code": python})
    assert (gone.status_code, gone.json()["code"]) == (404, "workspace.workspace.not_found")
    listing = await client.get(f"{API}/workspaces/{ws}/mounts")
    assert listing.status_code == 404


async def test_the_agent_right_reorder_and_unmount(client, workspace):
    python = (await _codex(client))["code"]
    vue = (await _codex(client, "vue"))["code"]
    ws = f"WORKSPACE@{workspace.code}"
    for code in (python, vue):
        await client.post(f"{API}/workspaces/{ws}/mounts", json={"codex_code": code})

    patched = await client.patch(
        f"{API}/workspaces/{ws}/mounts/{python}", json={"agent_can_edit": False}
    )
    assert (patched.status_code, patched.json()["agent_can_edit"]) == (200, False)

    order = await client.post(f"{API}/workspaces/{ws}/codexes/{vue}/reorder", json={"after_code": None})
    assert [m["codex"]["segment"] for m in order.json()] == ["vue", "python"]

    assert (await client.delete(f"{API}/workspaces/{ws}/mounts/{vue}")).status_code == 204
    # Switched off, still in its place — and listed as off, its right reading false.
    listed = (await client.get(f"{API}/workspaces/{ws}/codexes")).json()
    assert [(m["codex"]["segment"], m["mounted"], m["agent_can_edit"]) for m in listed] == [
        ("vue", False, False),
        ("python", True, False),
    ]
    missing = await client.delete(f"{API}/workspaces/{ws}/mounts/{vue}")
    assert (missing.status_code, missing.json()["code"]) == (404, "codex.mount.not_found")
    unmounted = await client.patch(
        f"{API}/workspaces/{ws}/mounts/{vue}", json={"agent_can_edit": True}
    )
    assert unmounted.status_code == 404
