"""HTTP API of the ``tasks`` module: groups (read) and tasks in full — from the list to purge.

What is checked is the surface's behaviour, not the CRUD beneath it: that an endpoint narrowed the
selection to the workspace asked about; that a status change set the phase stamp; that a move
changed the edge, not the card; that a soft delete is reversible and a hard one is not. The rules
of the store itself (branch cascade, workspace checks) live in ``test_task.py`` / ``test_link.py``.

The app with the router is brought up by the shared ``client`` fixture (``conftest.py``).
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from src.modules.tasks.constants import (
    CODE_LEN,
    PRIORITY_BURNING,
    SORT_DEFAULT,
    STATUS_CANCELED,
    STATUS_DONE,
    STATUS_IN_PROGRESS,
    TITLE_MAX,
    TYPE_STANDARD,
)
from src.modules.tasks.crud import group as group_crud
from src.modules.tasks.crud import link as link_crud
from src.modules.tasks.crud import task as task_crud
from src.modules.workspace.crud import workspace as workspace_crud

pytestmark = pytest.mark.db

GROUPS = "/internal/workbench/groups"
TASKS = "/internal/workbench/tasks"


async def _workspace(title: str = "Работа"):
    return await workspace_crud.workspace_create(title=title)


# ── groups ────────────────────────────────────────────────────────────────────


async def test_groups_are_scoped_to_the_asked_workspace(client):
    """A group lives inside a workspace: a neighbouring one never leaks into the response."""
    mine = await _workspace()
    stranger = await _workspace("Личное")
    await group_crud.group_create(workspace_code=mine.code, title="Биллинг")
    await group_crud.group_create(workspace_code=stranger.code, title="Дача")

    body = (await client.get(GROUPS, params={"workspace": mine.code})).json()

    assert [row["title"] for row in body] == ["Биллинг"]


async def test_groups_tag_the_code_with_its_type(client):
    """A group code in the output is a typed reference: ``TASKGROUP@`` tells it from a task code."""
    workspace = await _workspace()
    group = await group_crud.group_create(workspace_code=workspace.code, title="Биллинг")

    body = (await client.get(GROUPS, params={"workspace": workspace.code})).json()

    assert body[0]["code"] == f"TASKGROUP@{group.code}"
    assert body[0]["workspace_code"] == f"WORKSPACE@{workspace.code}"


async def test_groups_hide_deleted_without_the_flag(client):
    workspace = await _workspace()
    live = await group_crud.group_create(workspace_code=workspace.code, title="Живая")
    gone = await group_crud.group_create(workspace_code=workspace.code, title="Удалённая")
    await group_crud.group_delete(gone.code)

    without = (await client.get(GROUPS, params={"workspace": workspace.code})).json()
    with_flag = (
        await client.get(
            GROUPS, params={"workspace": workspace.code, "include_deleted": True}
        )
    ).json()

    assert [row["code"] for row in without] == [f"TASKGROUP@{live.code}"]
    assert len(with_flag) == 2


async def test_groups_of_a_missing_workspace_are_404(client):
    response = await client.get(GROUPS, params={"workspace": "0" * CODE_LEN})

    assert response.status_code == 404
    assert response.json()["code"] == "workspace.workspace.not_found"


# ── task list ─────────────────────────────────────────────────────────────────


async def test_task_list_is_scoped_to_the_asked_workspace(client):
    mine = await _workspace()
    stranger = await _workspace("Личное")
    await task_crud.task_create(workspace_code=mine.code, title="Счёт")
    await task_crud.task_create(workspace_code=stranger.code, title="Дача")

    body = (await client.get(TASKS, params={"workspace": mine.code})).json()

    assert [row["title"] for row in body] == ["Счёт"]


async def test_task_list_carries_the_tree_edge_and_the_branch_mark(client):
    """A list row answers both "where the task sits" and "is there anything below it"."""
    workspace = await _workspace()
    group = await group_crud.group_create(workspace_code=workspace.code, title="Биллинг")
    parent = await task_crud.task_create(
        workspace_code=workspace.code, title="Счета", group_code=group.code
    )
    child = await task_crud.task_create(
        workspace_code=workspace.code, title="Акт", parent_code=parent.code
    )

    body = (await client.get(TASKS, params={"workspace": workspace.code})).json()
    rows = {row["title"]: row for row in body}

    assert rows["Счета"]["parent_code"] is None
    assert rows["Счета"]["has_children"] is True
    assert rows["Счета"]["group_code"] == f"TASKGROUP@{group.code}"
    assert rows["Акт"]["parent_code"] == f"TASK@{parent.code}"
    assert rows["Акт"]["has_children"] is False
    assert rows["Акт"]["sort"] == SORT_DEFAULT
    assert rows["Акт"]["code"] == f"TASK@{child.code}"


async def test_task_list_orders_by_the_edge_sort(client):
    """The list order is the one the person arranged by hand, not the task's importance."""
    workspace = await _workspace()
    low = await task_crud.task_create(
        workspace_code=workspace.code, title="Ниже", priority=PRIORITY_BURNING
    )
    high = await task_crud.task_create(workspace_code=workspace.code, title="Выше")
    await link_crud.link_move(high.code, parent_code=None, sort=SORT_DEFAULT + 100)
    await link_crud.link_move(low.code, parent_code=None, sort=SORT_DEFAULT)

    body = (await client.get(TASKS, params={"workspace": workspace.code})).json()

    assert [row["title"] for row in body] == ["Выше", "Ниже"]


async def test_task_list_hides_deleted_without_the_flag(client):
    workspace = await _workspace()
    live = await task_crud.task_create(workspace_code=workspace.code, title="Живая")
    gone = await task_crud.task_create(workspace_code=workspace.code, title="Удалённая")
    await task_crud.task_delete(gone.code)

    without = (await client.get(TASKS, params={"workspace": workspace.code})).json()
    with_flag = (
        await client.get(
            TASKS, params={"workspace": workspace.code, "include_deleted": True}
        )
    ).json()

    assert [row["code"] for row in without] == [f"TASK@{live.code}"]
    assert len(with_flag) == 2


async def test_task_list_empty_group_asks_for_the_unassigned(client):
    """An empty ``group`` value means the "No group" section, not "no filter"."""
    workspace = await _workspace()
    group = await group_crud.group_create(workspace_code=workspace.code, title="Биллинг")
    await task_crud.task_create(
        workspace_code=workspace.code, title="В группе", group_code=group.code
    )
    await task_crud.task_create(workspace_code=workspace.code, title="Вне групп")

    loose = (
        await client.get(TASKS, params={"workspace": workspace.code, "group": ""})
    ).json()
    inside = (
        await client.get(TASKS, params={"workspace": workspace.code, "group": group.code})
    ).json()

    assert [row["title"] for row in loose] == ["Вне групп"]
    assert [row["title"] for row in inside] == ["В группе"]


async def test_task_list_narrows_by_status(client):
    workspace = await _workspace()
    done = await task_crud.task_create(workspace_code=workspace.code, title="Готово")
    await task_crud.task_update_status(done.code, STATUS_DONE)
    await task_crud.task_create(workspace_code=workspace.code, title="В очереди")

    body = (
        await client.get(
            TASKS, params={"workspace": workspace.code, "status": STATUS_DONE}
        )
    ).json()

    assert [row["title"] for row in body] == ["Готово"]


async def test_task_list_with_an_unknown_status_is_a_bad_request(client):
    """A value outside the dictionary is a mixed-up argument; the refusal names the allowed ones."""
    workspace = await _workspace()

    response = await client.get(
        TASKS, params={"workspace": workspace.code, "status": "на_потом"}
    )

    assert response.status_code == 400
    assert response.json()["error"]


# ── create ────────────────────────────────────────────────────────────────────


async def test_create_returns_201_and_the_whole_task(client):
    workspace = await _workspace()

    response = await client.post(
        TASKS,
        json={
            "workspace": f"WORKSPACE@{workspace.code}",
            "title": "Счёт",
            "description": "проверить начисления",
            "body": "# Заголовок",
            "type": TYPE_STANDARD,
            "priority": PRIORITY_BURNING,
            "deadline_at": "2026-09-20 18:00:00",
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["title"] == "Счёт"
    assert (body["type"], body["priority"]) == (TYPE_STANDARD, PRIORITY_BURNING)
    assert body["body"] == "# Заголовок"
    assert body["deadline_at"] == "2026-09-20 18:00:00"
    assert body["children"] == []
    assert len(body["code"].removeprefix("TASK@")) == CODE_LEN


async def test_create_puts_the_task_under_its_parent(client):
    workspace = await _workspace()
    parent = await task_crud.task_create(workspace_code=workspace.code, title="Счета")

    body = (
        await client.post(
            TASKS,
            json={
                "workspace": workspace.code,
                "title": "Акт",
                "parent_code": f"TASK@{parent.code}",
            },
        )
    ).json()

    assert body["parent_code"] == f"TASK@{parent.code}"


async def test_create_in_a_foreign_group_is_a_bad_request(client):
    """A group of another workspace is a wrong argument, not a missing record."""
    workspace = await _workspace()
    stranger = await _workspace("Личное")
    group = await group_crud.group_create(workspace_code=stranger.code, title="Дача")

    response = await client.post(
        TASKS,
        json={"workspace": workspace.code, "title": "Счёт", "group_code": group.code},
    )

    assert response.status_code == 400


async def test_create_rejects_a_blank_title(client):
    workspace = await _workspace()

    response = await client.post(
        TASKS, json={"workspace": workspace.code, "title": "   "}
    )

    assert response.status_code == 422


async def test_create_rejects_an_overlong_title(client):
    workspace = await _workspace()

    response = await client.post(
        TASKS, json={"workspace": workspace.code, "title": "я" * (TITLE_MAX + 1)}
    )

    assert response.status_code == 422


async def test_create_rejects_an_unknown_field(client):
    """A typo in a field name is a refusal, not silence.

    ``parent`` instead of ``parent_code`` used to give 201 and a task with no parent: the extra
    field was silently dropped, and the mismatch surfaced only as the task not landing in the
    branch. The extra field's name must arrive in ``fields`` — otherwise the refusal does not say
    what exactly to fix.
    """
    workspace = await _workspace()
    parent = await task_crud.task_create(workspace_code=workspace.code, title="Счета")

    response = await client.post(
        TASKS,
        json={"workspace": workspace.code, "title": "Акт", "parent": parent.code},
    )

    assert response.status_code == 422
    assert "parent" in response.json()["fields"]


async def test_update_rejects_an_unknown_field(client):
    """Extra fields are forbidden on ALL input bodies, not only on create.

    A status in the update body is the likeliest case: it has an endpoint of its own, and a status
    sent here used to just vanish, leaving "saved, but nothing changed".
    """
    workspace = await _workspace()
    task = await task_crud.task_create(workspace_code=workspace.code, title="Счёт")

    response = await client.put(
        f"{TASKS}/{task.code}", json={"title": "Счёт", "status": STATUS_DONE}
    )

    assert response.status_code == 422
    assert "status" in response.json()["fields"]


# ── read one ──────────────────────────────────────────────────────────────────


async def test_get_returns_the_children(client):
    workspace = await _workspace()
    parent = await task_crud.task_create(workspace_code=workspace.code, title="Счета")
    child = await task_crud.task_create(
        workspace_code=workspace.code, title="Акт", parent_code=parent.code
    )

    body = (await client.get(f"{TASKS}/{parent.code}")).json()

    assert [row["code"] for row in body["children"]] == [f"TASK@{child.code}"]
    assert body["has_children"] is True


async def test_get_accepts_both_code_forms(client):
    workspace = await _workspace()
    task = await task_crud.task_create(workspace_code=workspace.code, title="Счёт")

    bare = await client.get(f"{TASKS}/{task.code}")
    tagged = await client.get(f"{TASKS}/TASK@{task.code}")

    assert bare.status_code == tagged.status_code == 200
    assert bare.json() == tagged.json()


async def test_get_returns_a_deleted_task_with_its_buried_branch(client):
    """A trashed task's branch is trashed too — but it must be shown: decisions are made by it."""
    workspace = await _workspace()
    parent = await task_crud.task_create(workspace_code=workspace.code, title="Счета")
    await task_crud.task_create(
        workspace_code=workspace.code, title="Акт", parent_code=parent.code
    )
    await task_crud.task_delete(parent.code)

    body = (await client.get(f"{TASKS}/{parent.code}")).json()

    assert body["deleted_at"] is not None
    assert [row["title"] for row in body["children"]] == ["Акт"]


async def test_get_of_a_missing_task_is_404(client):
    response = await client.get(f"{TASKS}/{'0' * CODE_LEN}")

    assert response.status_code == 404
    assert response.json()["code"] == "tasks.task.not_found"
    assert response.json()["error"] == "Task not found"


async def test_a_foreign_code_prefix_is_a_bad_request(client):
    workspace = await _workspace()
    task = await task_crud.task_create(workspace_code=workspace.code, title="Счёт")

    response = await client.get(f"{TASKS}/TASKGROUP@{task.code}")

    assert response.status_code == 400


# ── update ────────────────────────────────────────────────────────────────────


async def test_update_replaces_the_card(client):
    workspace = await _workspace()
    group = await group_crud.group_create(workspace_code=workspace.code, title="Биллинг")
    task = await task_crud.task_create(
        workspace_code=workspace.code, title="Счёт", description="старое"
    )

    body = (
        await client.put(
            f"{TASKS}/{task.code}",
            json={
                "title": "Счёт за август",
                "description": "новое",
                "body": "текст",
                "type": TYPE_STANDARD,
                "priority": PRIORITY_BURNING,
                "group_code": f"TASKGROUP@{group.code}",
                "deadline_at": "2026-09-20 18:00:00",
            },
        )
    ).json()

    assert body["title"] == "Счёт за август"
    assert body["description"] == "новое"
    assert body["body"] == "текст"
    assert (body["type"], body["priority"]) == (TYPE_STANDARD, PRIORITY_BURNING)
    assert body["group_code"] == f"TASKGROUP@{group.code}"
    assert body["deadline_at"] == "2026-09-20 18:00:00"


async def test_update_clears_what_the_body_omits(client):
    """Full replace: an omitted group and dates are cleared — otherwise nothing could erase them."""
    workspace = await _workspace()
    group = await group_crud.group_create(workspace_code=workspace.code, title="Биллинг")
    task = await task_crud.task_create(
        workspace_code=workspace.code,
        title="Счёт",
        group_code=group.code,
        deadline_at=datetime(2026, 9, 20, 18, 0, tzinfo=UTC),
    )

    body = (await client.put(f"{TASKS}/{task.code}", json={"title": "Счёт"})).json()

    assert body["group_code"] is None
    assert body["deadline_at"] is None


async def test_update_does_not_touch_the_status(client):
    """A full replace of the card does not erase the status: the update body has no such field.

    The body is sent without a status — exactly how the form sends it. Trying to pass a status
    here is now a refusal (see ``test_update_rejects_an_unknown_field``), not a silent ignore.
    """
    workspace = await _workspace()
    task = await task_crud.task_create(workspace_code=workspace.code, title="Счёт")
    await task_crud.task_update_status(task.code, STATUS_IN_PROGRESS)

    body = (await client.put(f"{TASKS}/{task.code}", json={"title": "Счёт"})).json()

    assert body["status"] == STATUS_IN_PROGRESS


async def test_update_of_a_deleted_task_is_409(client):
    workspace = await _workspace()
    task = await task_crud.task_create(workspace_code=workspace.code, title="Счёт")
    await task_crud.task_delete(task.code)

    response = await client.put(f"{TASKS}/{task.code}", json={"title": "Счёт"})

    assert response.status_code == 409
    assert response.json()["code"] == "tasks.task.deleted"


# ── status ────────────────────────────────────────────────────────────────────


async def test_status_stamps_the_phase(client):
    """Start, completion and cancellation are facts with their own dates, not one ``status``."""
    workspace = await _workspace()
    task = await task_crud.task_create(workspace_code=workspace.code, title="Счёт")

    started = (
        await client.post(
            f"{TASKS}/{task.code}/status", json={"status": STATUS_IN_PROGRESS}
        )
    ).json()
    done = (
        await client.post(f"{TASKS}/{task.code}/status", json={"status": STATUS_DONE})
    ).json()

    assert started["started_at"] is not None
    assert started["completed_at"] is None
    assert done["status"] == STATUS_DONE
    assert done["completed_at"] is not None


async def test_status_keeps_the_first_stamp(client):
    """Resuming work does not rewrite when the task was started: that is a fact, not a state."""
    workspace = await _workspace()
    task = await task_crud.task_create(workspace_code=workspace.code, title="Счёт")
    first = (
        await client.post(
            f"{TASKS}/{task.code}/status", json={"status": STATUS_IN_PROGRESS}
        )
    ).json()
    await client.post(f"{TASKS}/{task.code}/status", json={"status": STATUS_CANCELED})

    again = (
        await client.post(
            f"{TASKS}/{task.code}/status", json={"status": STATUS_IN_PROGRESS}
        )
    ).json()

    assert again["started_at"] == first["started_at"]
    assert again["canceled_at"] is not None


async def test_status_outside_the_dictionary_is_a_bad_request(client):
    workspace = await _workspace()
    task = await task_crud.task_create(workspace_code=workspace.code, title="Счёт")

    response = await client.post(
        f"{TASKS}/{task.code}/status", json={"status": "почти_готово"}
    )

    assert response.status_code == 400


async def test_status_of_a_deleted_task_is_409(client):
    workspace = await _workspace()
    task = await task_crud.task_create(workspace_code=workspace.code, title="Счёт")
    await task_crud.task_delete(task.code)

    response = await client.post(
        f"{TASKS}/{task.code}/status", json={"status": STATUS_DONE}
    )

    assert response.status_code == 409


# ── move ──────────────────────────────────────────────────────────────────────


async def test_move_changes_the_edge(client):
    workspace = await _workspace()
    parent = await task_crud.task_create(workspace_code=workspace.code, title="Счета")
    task = await task_crud.task_create(workspace_code=workspace.code, title="Акт")

    body = (
        await client.post(
            f"{TASKS}/{task.code}/move",
            json={"parent_code": f"TASK@{parent.code}", "sort": 700},
        )
    ).json()

    assert body["parent_code"] == f"TASK@{parent.code}"
    assert body["sort"] == 700


async def test_move_to_the_root_empties_the_parent(client):
    workspace = await _workspace()
    parent = await task_crud.task_create(workspace_code=workspace.code, title="Счета")
    task = await task_crud.task_create(
        workspace_code=workspace.code, title="Акт", parent_code=parent.code
    )

    body = (await client.post(f"{TASKS}/{task.code}/move", json={})).json()

    assert body["parent_code"] is None


async def test_move_under_own_child_is_a_bad_request(client):
    """A branch under its own descendant would break off the tree into a closed loop."""
    workspace = await _workspace()
    root = await task_crud.task_create(workspace_code=workspace.code, title="Счета")
    child = await task_crud.task_create(
        workspace_code=workspace.code, title="Акт", parent_code=root.code
    )

    response = await client.post(
        f"{TASKS}/{root.code}/move", json={"parent_code": child.code}
    )

    assert response.status_code == 400


async def test_move_rejects_an_unknown_field(client):
    """The move body is ``extra=forbid``: a typo in a field name is a 422, not a silent pass."""
    workspace = await _workspace()
    task = await task_crud.task_create(workspace_code=workspace.code, title="Акт")

    response = await client.post(
        f"{TASKS}/{task.code}/move", json={"group_name": "Сначала"}
    )

    assert response.status_code == 422


# ── delete, restore, purge ────────────────────────────────────────────────────


async def test_delete_buries_the_whole_branch(client):
    workspace = await _workspace()
    parent = await task_crud.task_create(workspace_code=workspace.code, title="Счета")
    child = await task_crud.task_create(
        workspace_code=workspace.code, title="Акт", parent_code=parent.code
    )

    response = await client.delete(f"{TASKS}/{parent.code}")

    assert response.status_code == 204
    assert (await task_crud.task_get(parent.code)) is None
    assert (await task_crud.task_get(child.code)) is None


async def test_restore_raises_the_branch_that_went_down_together(client):
    workspace = await _workspace()
    parent = await task_crud.task_create(workspace_code=workspace.code, title="Счета")
    child = await task_crud.task_create(
        workspace_code=workspace.code, title="Акт", parent_code=parent.code
    )
    await client.delete(f"{TASKS}/{parent.code}")

    body = (await client.post(f"{TASKS}/{parent.code}/restore")).json()

    assert body["deleted_at"] is None
    assert (await task_crud.task_get(child.code)) is not None


async def test_restore_of_a_live_task_is_409(client):
    """A click on the wrong row: a silent "ok" would hide that the screen and the DB disagree."""
    workspace = await _workspace()
    task = await task_crud.task_create(workspace_code=workspace.code, title="Счёт")

    response = await client.post(f"{TASKS}/{task.code}/restore")

    assert response.status_code == 409


async def test_purge_removes_the_branch_physically(client):
    workspace = await _workspace()
    parent = await task_crud.task_create(workspace_code=workspace.code, title="Счета")
    child = await task_crud.task_create(
        workspace_code=workspace.code, title="Акт", parent_code=parent.code
    )

    response = await client.delete(f"{TASKS}/{parent.code}/purge")

    assert response.status_code == 204
    assert (await task_crud.task_get(parent.code, include_deleted=True)) is None
    assert (await task_crud.task_get(child.code, include_deleted=True)) is None
    assert (await link_crud.link_get(child.code)) is None


async def test_purge_leaves_the_neighbours_alone(client):
    workspace = await _workspace()
    doomed = await task_crud.task_create(workspace_code=workspace.code, title="Под снос")
    kept = await task_crud.task_create(workspace_code=workspace.code, title="Остаётся")

    await client.delete(f"{TASKS}/{doomed.code}/purge")

    assert (await task_crud.task_get(kept.code)) is not None


async def test_purge_of_a_missing_task_is_404(client):
    response = await client.delete(f"{TASKS}/{'0' * CODE_LEN}/purge")

    assert response.status_code == 404


async def test_get_names_the_group_and_the_parent(client):
    """The group and the parent ship as rows: the page shows them by title, not by code."""
    workspace = await _workspace()
    group = await group_crud.group_create(workspace_code=workspace.code, title="Биллинг")
    parent = await task_crud.task_create(
        workspace_code=workspace.code, title="Счета", group_code=group.code
    )
    task = await task_crud.task_create(
        workspace_code=workspace.code, title="Акт", parent_code=parent.code
    )

    body = (await client.get(f"{TASKS}/{task.code}")).json()

    assert body["group"]["title"] == "Биллинг"
    assert body["parent"]["title"] == "Счета"
    assert body["parent"]["code"] == f"TASK@{parent.code}"


async def test_get_of_a_root_task_has_no_parent(client):
    workspace = await _workspace()
    task = await task_crud.task_create(workspace_code=workspace.code, title="Счета")

    body = (await client.get(f"{TASKS}/{task.code}")).json()

    assert body["parent"] is None
    assert body["group"] is None


# ── Dragging a list row ───────────────────────────────────────────────────────


async def test_reorder_moves_the_task_after_the_named_neighbour(client):
    workspace = await _workspace()
    first = await task_crud.task_create(workspace_code=workspace.code, title="Первая")
    second = await task_crud.task_create(workspace_code=workspace.code, title="Вторая")
    third = await task_crud.task_create(workspace_code=workspace.code, title="Третья")

    response = await client.post(
        f"{TASKS}/{third.code}/reorder", json={"after_code": f"TASK@{first.code}"}
    )

    assert response.status_code == 200
    codes = [
        row["code"]
        for row in (
            await client.get(TASKS, params={"workspace": f"WORKSPACE@{workspace.code}"})
        ).json()
    ]
    assert codes == [f"TASK@{first.code}", f"TASK@{third.code}", f"TASK@{second.code}"]


async def test_reorder_carries_the_task_into_another_group(client):
    """Dragging into another card changes the group and the position in one request."""
    workspace = await _workspace()
    billing = await group_crud.group_create(workspace_code=workspace.code, title="Биллинг")
    docs = await group_crud.group_create(workspace_code=workspace.code, title="Документы")
    task = await task_crud.task_create(
        workspace_code=workspace.code, title="Счёт", group_code=billing.code
    )

    body = (
        await client.post(
            f"{TASKS}/{task.code}/reorder",
            json={"after_code": None, "group_code": f"TASKGROUP@{docs.code}"},
        )
    ).json()

    assert body["group_code"] == f"TASKGROUP@{docs.code}"


async def test_reorder_can_take_the_group_off(client):
    """`null` in the body unsets the group: the row was dragged into the "No group" card."""
    workspace = await _workspace()
    group = await group_crud.group_create(workspace_code=workspace.code, title="Биллинг")
    task = await task_crud.task_create(
        workspace_code=workspace.code, title="Счёт", group_code=group.code
    )

    body = (
        await client.post(
            f"{TASKS}/{task.code}/reorder", json={"after_code": None, "group_code": None}
        )
    ).json()

    assert body["group_code"] is None


async def test_reorder_without_the_group_key_keeps_the_group(client):
    """No key, the group is left alone: reordering within its own card knows nothing of groups."""
    workspace = await _workspace()
    group = await group_crud.group_create(workspace_code=workspace.code, title="Биллинг")
    task = await task_crud.task_create(
        workspace_code=workspace.code, title="Счёт", group_code=group.code
    )

    body = (
        await client.post(f"{TASKS}/{task.code}/reorder", json={"after_code": None})
    ).json()

    assert body["group_code"] == f"TASKGROUP@{group.code}"


async def test_reorder_detaches_the_subtask_in_one_request(client):
    """The list's second gesture: a subtask dragged from its branch into a group card is a root."""
    workspace = await _workspace()
    group = await group_crud.group_create(workspace_code=workspace.code, title="Биллинг")
    parent = await task_crud.task_create(workspace_code=workspace.code, title="Эпик")
    neighbour = await task_crud.task_create(
        workspace_code=workspace.code, title="Сосед по карточке", group_code=group.code
    )
    child = await task_crud.task_create(
        workspace_code=workspace.code, title="Подзадача", parent_code=parent.code
    )

    body = (
        await client.post(
            f"{TASKS}/{child.code}/reorder",
            json={
                "parent_code": None,
                "group_code": f"TASKGROUP@{group.code}",
                "after_code": f"TASK@{neighbour.code}",
            },
        )
    ).json()

    assert body["parent_code"] is None
    assert body["group_code"] == f"TASKGROUP@{group.code}"
    # It landed right below the named neighbour — that is, where it was dropped, not at row end.
    row = await link_crud.link_list_by_parent(None)
    codes = [item.task_code for item in row if item.task_code in {neighbour.code, child.code}]
    assert codes == [neighbour.code, child.code]


async def test_reorder_detaches_a_subtask_of_a_filed_epic_into_another_card(client):
    """A subtask's group is only its parent's, so detaching and regrouping are one write.

    In two steps (group first, then parent) the gesture would hit that ban on the very first one.
    """
    workspace = await _workspace()
    billing = await group_crud.group_create(workspace_code=workspace.code, title="Биллинг")
    interface = await group_crud.group_create(workspace_code=workspace.code, title="Интерфейс")
    parent = await task_crud.task_create(
        workspace_code=workspace.code, title="Эпик", group_code=billing.code
    )
    child = await task_crud.task_create(
        workspace_code=workspace.code, title="Подзадача", parent_code=parent.code
    )

    response = await client.post(
        f"{TASKS}/{child.code}/reorder",
        json={"parent_code": None, "group_code": f"TASKGROUP@{interface.code}", "after_code": None},
    )

    assert response.status_code == 200
    assert response.json()["parent_code"] is None
    assert response.json()["group_code"] == f"TASKGROUP@{interface.code}"


@pytest.mark.parametrize("gesture", ["parent", "group"])
async def test_reorder_with_a_wrong_neighbour_writes_nothing(client, gesture):
    """A wrong neighbour (a stale screen) is a 400, and the move rolls back with the position."""
    workspace = await _workspace()
    billing = await group_crud.group_create(workspace_code=workspace.code, title="Биллинг")
    interface = await group_crud.group_create(workspace_code=workspace.code, title="Интерфейс")
    epic = await task_crud.task_create(
        workspace_code=workspace.code, title="Эпик", group_code=interface.code
    )
    stranger = await task_crud.task_create(
        workspace_code=workspace.code, title="Не сосед", group_code=billing.code
    )
    moved = await task_crud.task_create(
        workspace_code=workspace.code, title="Тащат", group_code=billing.code
    )
    before = (await link_crud.link_get(moved.code)).sort
    tree_change = (
        {"parent_code": f"TASK@{epic.code}"}
        if gesture == "parent"
        else {"group_code": f"TASKGROUP@{interface.code}"}
    )

    response = await client.post(
        f"{TASKS}/{moved.code}/reorder",
        json={"after_code": f"TASK@{stranger.code}", **tree_change},
    )

    assert response.status_code == 400
    link = await link_crud.link_get(moved.code)
    assert link.parent_code is None
    assert link.sort == before
    assert (await task_crud.task_get(moved.code)).group_code == billing.code


async def test_move_refuses_a_parent_in_the_bin(client):
    workspace = await _workspace()
    parent = await task_crud.task_create(workspace_code=workspace.code, title="Эпик")
    loose = await task_crud.task_create(workspace_code=workspace.code, title="Отдельная")
    await task_crud.task_delete(parent.code)

    response = await client.post(
        f"{TASKS}/{loose.code}/move", json={"parent_code": f"TASK@{parent.code}"}
    )

    assert response.status_code == 400
    assert (await link_crud.link_get(loose.code)).parent_code is None


async def test_reorder_without_the_parent_key_keeps_the_branch(client):
    """No key, the parent is left alone: reordering among siblings knows nothing of the tree."""
    workspace = await _workspace()
    parent = await task_crud.task_create(workspace_code=workspace.code, title="Эпик")
    first = await task_crud.task_create(
        workspace_code=workspace.code, title="Первая", parent_code=parent.code
    )
    second = await task_crud.task_create(
        workspace_code=workspace.code, title="Вторая", parent_code=parent.code
    )

    body = (
        await client.post(
            f"{TASKS}/{second.code}/reorder", json={"after_code": None}
        )
    ).json()

    assert body["parent_code"] == f"TASK@{parent.code}"
    row = await link_crud.link_list_by_parent(parent.code)
    assert [item.task_code for item in row] == [second.code, first.code]


async def test_reorder_refuses_to_hang_a_task_under_its_own_child(client):
    """A loop is a broken tree, not an odd layout: 400, and nothing is touched."""
    workspace = await _workspace()
    parent = await task_crud.task_create(workspace_code=workspace.code, title="Эпик")
    child = await task_crud.task_create(
        workspace_code=workspace.code, title="Подзадача", parent_code=parent.code
    )

    response = await client.post(
        f"{TASKS}/{parent.code}/reorder", json={"parent_code": f"TASK@{child.code}"}
    )

    assert response.status_code == 400
    assert (await link_crud.link_get(parent.code)).parent_code is None


async def test_reorder_refuses_a_neighbour_from_another_row(client):
    workspace = await _workspace()
    parent = await task_crud.task_create(workspace_code=workspace.code, title="Эпик")
    other = await task_crud.task_create(workspace_code=workspace.code, title="Другой корень")
    child = await task_crud.task_create(
        workspace_code=workspace.code, title="Подзадача", parent_code=parent.code
    )

    response = await client.post(
        f"{TASKS}/{child.code}/reorder", json={"after_code": f"TASK@{other.code}"}
    )

    assert response.status_code == 400


async def test_reorder_refuses_a_deleted_task(client):
    workspace = await _workspace()
    task = await task_crud.task_create(workspace_code=workspace.code, title="Счёт")
    await task_crud.task_delete(task.code)

    response = await client.post(f"{TASKS}/{task.code}/reorder", json={"after_code": None})

    assert response.status_code == 409
