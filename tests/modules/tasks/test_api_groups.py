"""HTTP API of the ``tasks`` module: writes on groups — create, update and both deletes.

Reading groups lives in ``test_api_tasks.py`` (there it sits next to the task list that groups
lay out). Here is what arrived together with their section: the task counter in a list row, the
refusal to edit something deleted, and the different fate of tasks under the two deletes.

The app with the router is brought up by the shared ``client`` fixture (``conftest.py``).
"""

from __future__ import annotations

import pytest

from src.modules.tasks.constants import CODE_LEN, GROUP_DESCRIPTION_MAX, SORT_DEFAULT
from src.modules.tasks.crud import group as group_crud
from src.modules.tasks.crud import task as task_crud
from src.modules.workspace.crud import workspace as workspace_crud

pytestmark = pytest.mark.db

GROUPS = "/internal/workbench/groups"


async def _workspace(title: str = "Работа"):
    return await workspace_crud.workspace_create(title=title)


# ── counter ───────────────────────────────────────────────────────────────────


async def test_list_counts_only_live_tasks_of_the_group(client):
    """The counter tells what the person will find inside: a deleted task does not count."""
    workspace = await _workspace()
    group = await group_crud.group_create(workspace_code=workspace.code, title="Биллинг")
    await task_crud.task_create(
        workspace_code=workspace.code, group_code=group.code, title="Счёт"
    )
    gone = await task_crud.task_create(
        workspace_code=workspace.code, group_code=group.code, title="Отменённая"
    )
    await task_crud.task_delete(gone.code)

    body = (await client.get(GROUPS, params={"workspace": workspace.code})).json()

    assert body[0]["task_count"] == 1


async def test_list_counts_zero_for_an_empty_group(client):
    workspace = await _workspace()
    await group_crud.group_create(workspace_code=workspace.code, title="Пустая")

    body = (await client.get(GROUPS, params={"workspace": workspace.code})).json()

    assert body[0]["task_count"] == 0


# ── create ────────────────────────────────────────────────────────────────────


async def test_create_puts_the_group_in_the_asked_workspace(client):
    workspace = await _workspace()

    response = await client.post(
        GROUPS, params={"workspace": workspace.code}, json={"title": "Биллинг"}
    )

    assert response.status_code == 201
    assert response.json()["workspace_code"] == f"WORKSPACE@{workspace.code}"
    assert response.json()["sort"] == SORT_DEFAULT


async def test_lower_case_codes_in_the_path_and_query_find_their_rows(client):
    """A bookmark or a link from before codes went upper case still opens what it pointed at."""
    workspace = await _workspace()
    group = await group_crud.group_create(workspace_code=workspace.code, title="Биллинг")

    listed = await client.get(GROUPS, params={"workspace": workspace.code.lower()})
    one = await client.get(f"{GROUPS}/taskgroup@{group.code.lower()}")

    assert [row["code"] for row in listed.json()] == [f"TASKGROUP@{group.code}"]
    assert one.status_code == 200
    assert one.json()["code"] == f"TASKGROUP@{group.code}"


async def test_a_code_under_the_retired_group_prefix_still_finds_its_row(client):
    """``GROUP@`` links written before the rename keep opening; the answer uses the new word."""
    workspace = await _workspace()
    group = await group_crud.group_create(workspace_code=workspace.code, title="Биллинг")

    one = await client.get(f"{GROUPS}/GROUP@{group.code}")

    assert one.status_code == 200
    assert one.json()["code"] == f"TASKGROUP@{group.code}"


async def test_create_in_a_missing_workspace_is_404(client):
    response = await client.post(
        GROUPS, params={"workspace": "0" * CODE_LEN}, json={"title": "Биллинг"}
    )

    assert response.status_code == 404


async def test_create_rejects_an_unknown_field(client):
    """A typo in a field name is a refusal, not a silently ignored value (``extra=forbid``)."""
    workspace = await _workspace()

    response = await client.post(
        GROUPS,
        params={"workspace": workspace.code},
        json={"title": "Биллинг", "workspace_code": workspace.code},
    )

    assert response.status_code == 422


@pytest.mark.parametrize(
    ("length", "status"), [(GROUP_DESCRIPTION_MAX, 201), (GROUP_DESCRIPTION_MAX + 1, 422)]
)
async def test_create_holds_the_description_limit(client, length, status):
    workspace = await _workspace()

    response = await client.post(
        GROUPS,
        params={"workspace": workspace.code},
        json={"title": "Биллинг", "description": "д" * length},
    )

    assert response.status_code == status


# ── update ────────────────────────────────────────────────────────────────────


async def test_update_replaces_the_whole_card(client):
    """An update is a full replace: an omitted field is erased, not left as it was."""
    workspace = await _workspace()
    group = await group_crud.group_create(
        workspace_code=workspace.code, title="Биллинг", description="Старое", icon="flask"
    )

    body = (
        await client.put(f"{GROUPS}/{group.code}", json={"title": "Оплаты", "sort": 700})
    ).json()

    assert (body["title"], body["description"], body["icon"], body["sort"]) == (
        "Оплаты",
        "",
        "",
        700,
    )


async def test_update_of_a_deleted_group_is_409(client):
    """Deleted is not editable — restore first; 409, not 404: the group is there on screen."""
    workspace = await _workspace()
    group = await group_crud.group_create(workspace_code=workspace.code, title="Биллинг")
    await group_crud.group_delete(group.code)

    response = await client.put(f"{GROUPS}/{group.code}", json={"title": "Оплаты"})

    assert response.status_code == 409


async def test_update_wont_move_the_group_between_workspaces(client):
    """The update body has no workspace at all: moving a group would drag all its tasks along."""
    workspace = await _workspace()
    stranger = await _workspace("Личное")
    group = await group_crud.group_create(workspace_code=workspace.code, title="Биллинг")

    response = await client.put(
        f"{GROUPS}/{group.code}", json={"title": "Биллинг", "workspace": stranger.code}
    )

    assert response.status_code == 422


# ── delete ────────────────────────────────────────────────────────────────────


async def _group_with_tasks():
    """A group holding a root with a subtask and a task already in the trash, plus a second group."""
    workspace = await _workspace()
    group = await group_crud.group_create(workspace_code=workspace.code, title="Биллинг")
    other = await group_crud.group_create(workspace_code=workspace.code, title="Инфра")
    root = await task_crud.task_create(
        workspace_code=workspace.code, group_code=group.code, title="Эпик"
    )
    child = await task_crud.task_create(
        workspace_code=workspace.code, parent_code=root.code, title="Часть"
    )
    trashed = await task_crud.task_create(
        workspace_code=workspace.code, group_code=group.code, title="Старая"
    )
    await task_crud.task_delete(trashed.code)
    return workspace, group, other, root, child, trashed


async def _group_of(code: str) -> str | None:
    return (await task_crud.task_get(code, include_deleted=True)).group_code


async def test_deleting_a_group_with_live_tasks_needs_their_fate(client):
    """Without a choice the tasks would point at a group nothing draws and vanish from the list."""
    _, group, _, root, _, _ = await _group_with_tasks()

    response = await client.delete(f"{GROUPS}/{group.code}")

    assert response.status_code == 409
    assert response.json()["code"] == "tasks.group.has_tasks"
    assert (await group_crud.group_get(group.code)).deleted_at is None
    assert await _group_of(root.code) == group.code


async def test_ungroup_takes_every_task_off_the_group_trashed_ones_too(client):
    _, group, _, root, child, trashed = await _group_with_tasks()

    response = await client.delete(f"{GROUPS}/{group.code}", params={"tasks": "ungroup"})

    assert response.status_code == 204
    assert (await group_crud.group_get(group.code, include_deleted=True)).deleted_at is not None
    assert [await _group_of(t.code) for t in (root, child, trashed)] == [None, None, None]
    assert (await task_crud.task_get(root.code)).deleted_at is None


async def test_move_files_every_task_under_the_target(client):
    _, group, other, root, child, trashed = await _group_with_tasks()

    response = await client.delete(
        f"{GROUPS}/{group.code}", params={"tasks": "move", "target": f"TASKGROUP@{other.code}"}
    )

    assert response.status_code == 204
    assert [await _group_of(t.code) for t in (root, child, trashed)] == [other.code] * 3


@pytest.mark.parametrize("target", ["self", "missing", "none"])
async def test_move_refuses_a_target_that_is_not_another_live_group(client, target):
    _, group, _, root, _, _ = await _group_with_tasks()
    params = {"tasks": "move"}
    if target == "self":
        params["target"] = group.code
    elif target == "missing":
        params["target"] = "0" * CODE_LEN

    response = await client.delete(f"{GROUPS}/{group.code}", params=params)

    assert response.status_code == 400
    assert (await group_crud.group_get(group.code)).deleted_at is None
    assert await _group_of(root.code) == group.code


async def test_delete_trashes_the_live_tasks_and_their_branches(client):
    """A task restored later lands in "No group", not back in a group that is gone."""
    _, group, _, root, child, trashed = await _group_with_tasks()

    response = await client.delete(f"{GROUPS}/{group.code}", params={"tasks": "delete"})

    assert response.status_code == 204
    assert await task_crud.task_get(root.code) is None
    assert await task_crud.task_get(child.code) is None
    assert [await _group_of(t.code) for t in (root, child, trashed)] == [None, None, None]
    assert await task_crud.task_restore(root.code)
    restored = await task_crud.task_get(child.code)
    assert restored is not None and restored.group_code is None


async def test_a_group_with_only_trashed_tasks_needs_no_choice(client):
    workspace = await _workspace()
    group = await group_crud.group_create(workspace_code=workspace.code, title="Биллинг")
    gone = await task_crud.task_create(
        workspace_code=workspace.code, group_code=group.code, title="Старая"
    )
    await task_crud.task_delete(gone.code)

    assert (await client.delete(f"{GROUPS}/{group.code}")).status_code == 204
    assert await _group_of(gone.code) is None


async def test_an_unknown_fate_is_refused(client):
    _, group, _, _, _, _ = await _group_with_tasks()

    response = await client.delete(f"{GROUPS}/{group.code}", params={"tasks": "archive"})

    assert response.status_code == 400


async def test_restore_brings_the_group_back(client):
    workspace = await _workspace()
    group = await group_crud.group_create(workspace_code=workspace.code, title="Биллинг")
    await group_crud.group_delete(group.code)

    body = (await client.post(f"{GROUPS}/{group.code}/restore")).json()

    assert body["deleted_at"] is None


async def test_restore_of_a_live_group_is_409(client):
    """A live one has nothing to restore: a silent "ok" would hide a click on the wrong row."""
    workspace = await _workspace()
    group = await group_crud.group_create(workspace_code=workspace.code, title="Биллинг")

    response = await client.post(f"{GROUPS}/{group.code}/restore")

    assert response.status_code == 409
    assert response.json()["code"] == "tasks.group.not_deleted"


async def test_purge_drops_the_group_and_unsorts_its_tasks(client):
    """Purging a group is not purging work: the task outlives it in "No group" (FK SET NULL)."""
    workspace = await _workspace()
    group = await group_crud.group_create(workspace_code=workspace.code, title="Биллинг")
    task = await task_crud.task_create(
        workspace_code=workspace.code, group_code=group.code, title="Счёт"
    )

    assert (await client.delete(f"{GROUPS}/{group.code}/purge")).status_code == 204

    assert await group_crud.group_get(group.code, include_deleted=True) is None
    assert (await task_crud.task_get(task.code)).group_code is None


async def test_purge_of_a_missing_group_is_404(client):
    response = await client.delete(f"{GROUPS}/{'0' * CODE_LEN}/purge")

    assert response.status_code == 404


# ── reorder ───────────────────────────────────────────────────────────────────


async def test_reorder_puts_the_group_right_under_its_anchor(client):
    """The position is named by a neighbour: "under Billing" is a place, not a ``sort`` number."""
    workspace = await _workspace()
    first = await group_crud.group_create(workspace_code=workspace.code, title="Биллинг")
    second = await group_crud.group_create(workspace_code=workspace.code, title="Интерфейс")
    third = await group_crud.group_create(workspace_code=workspace.code, title="Сборка")

    response = await client.post(
        f"{GROUPS}/{third.code}/reorder", json={"after_code": first.code}
    )

    assert response.status_code == 200
    rows = await group_crud.group_list_by_workspace(workspace.code)
    assert [row.code for row in rows] == [first.code, third.code, second.code]


async def test_reorder_accepts_the_anchor_with_its_prefix(client):
    """The neighbour's code is accepted in the same form it ships in within the group list."""
    workspace = await _workspace()
    first = await group_crud.group_create(workspace_code=workspace.code, title="Биллинг")
    second = await group_crud.group_create(workspace_code=workspace.code, title="Интерфейс")

    response = await client.post(
        f"{GROUPS}/{second.code}/reorder", json={"before_code": f"TASKGROUP@{first.code}"}
    )

    assert response.status_code == 200
    rows = await group_crud.group_list_by_workspace(workspace.code)
    assert [row.code for row in rows] == [second.code, first.code]


async def test_reorder_without_a_reference_point_is_400(client):
    """No reference point at all is not "anywhere" but an unspecified place."""
    workspace = await _workspace()
    group = await group_crud.group_create(workspace_code=workspace.code, title="Биллинг")

    response = await client.post(f"{GROUPS}/{group.code}/reorder", json={})

    assert response.status_code == 400


async def test_reorder_with_both_reference_points_is_400(client):
    workspace = await _workspace()
    first = await group_crud.group_create(workspace_code=workspace.code, title="Биллинг")
    second = await group_crud.group_create(workspace_code=workspace.code, title="Интерфейс")

    response = await client.post(
        f"{GROUPS}/{first.code}/reorder",
        json={"after_code": second.code, "before_code": second.code},
    )

    assert response.status_code == 400


async def test_reorder_against_a_stranger_is_400(client):
    """A layout never crosses workspaces: a foreign neighbour is a caller error, not a lost row."""
    mine = await _workspace()
    stranger = await _workspace("Личное")
    group = await group_crud.group_create(workspace_code=mine.code, title="Биллинг")
    alien = await group_crud.group_create(workspace_code=stranger.code, title="Дача")

    response = await client.post(
        f"{GROUPS}/{group.code}/reorder", json={"after_code": alien.code}
    )

    assert response.status_code == 400


async def test_reorder_of_a_missing_group_is_404(client):
    workspace = await _workspace()
    anchor = await group_crud.group_create(workspace_code=workspace.code, title="Биллинг")

    response = await client.post(
        f"{GROUPS}/{'0' * CODE_LEN}/reorder", json={"after_code": anchor.code}
    )

    assert response.status_code == 404
