"""HTTP API of the ``workspace`` module (/internal/workspace): the workspace whole — list to purge.

Only the entity itself and its counters as a MECHANISM live here: what happens to zones and tasks
when a workspace is deleted is checked in the tests of the module that owns them
(``tests/modules/tasks/test_workspace_cascade.py``). A level-1 module must be testable on its
own — without a single table of the modules above it.

The app with the router is brought up by the shared ``client`` fixture (``conftest.py``); it also
clears the counter registry, so by default the list in the response is empty.
"""

from __future__ import annotations

import pytest

from src.modules.workspace.constants import CODE_LEN, DESCRIPTION_MAX, SORT_DEFAULT, TITLE_MAX
from src.modules.workspace.crud import workspace as workspace_crud
from src.modules.workspace.stats import WorkspaceCounter, register_counter

pytestmark = pytest.mark.db

BASE = "/internal/workspace"


# ── list ──────────────────────────────────────────────────────────────────────


async def test_list_orders_by_sort_then_title(client):
    await workspace_crud.workspace_create(title="Личное", sort=SORT_DEFAULT)
    await workspace_crud.workspace_create(title="Автономия", sort=SORT_DEFAULT)
    await workspace_crud.workspace_create(title="Работа", sort=SORT_DEFAULT + 100)

    body = (await client.get(BASE)).json()

    assert [row["title"] for row in body] == ["Работа", "Автономия", "Личное"]
    assert [row["sort"] for row in body] == [SORT_DEFAULT + 100, SORT_DEFAULT, SORT_DEFAULT]


async def test_create_takes_the_sort_and_defaults_it(client):
    placed = await client.post(BASE, json={"title": "Работа", "sort": 900})
    plain = await client.post(BASE, json={"title": "Личное"})

    assert placed.json()["sort"] == 900
    assert plain.json()["sort"] == SORT_DEFAULT


async def test_update_replaces_the_sort(client):
    row = await workspace_crud.workspace_create(title="Работа", sort=900)

    body = (await client.put(f"{BASE}/{row.code}", json={"title": "Работа", "sort": 0})).json()

    assert body["sort"] == 0
    assert (await workspace_crud.workspace_get(row.code)).sort == 0


async def test_create_refuses_a_non_integer_sort(client):
    response = await client.post(BASE, json={"title": "Работа", "sort": "наверх"})

    assert response.status_code == 422


async def test_list_tags_the_code_with_its_type(client):
    """The code in the output is a typed ref: ``WORKSPACE@`` tells it apart from the codes above."""
    row = await workspace_crud.workspace_create(title="Работа")

    body = (await client.get(BASE)).json()

    assert body[0]["code"] == f"WORKSPACE@{row.code}"


async def test_list_hides_deleted_without_the_flag(client):
    live = await workspace_crud.workspace_create(title="Живое")
    gone = await workspace_crud.workspace_create(title="Удалённое")
    await workspace_crud.workspace_delete(gone.code)

    body = (await client.get(BASE)).json()

    assert [row["code"] for row in body] == [f"WORKSPACE@{live.code}"]


async def test_list_shows_deleted_with_the_flag(client):
    gone = await workspace_crud.workspace_create(title="Удалённое")
    await workspace_crud.workspace_delete(gone.code)

    body = (await client.get(BASE, params={"include_deleted": True})).json()

    assert [row["title"] for row in body] == ["Удалённое"]
    assert body[0]["deleted_at"] is not None


# ── content counters (extension point) ────────────────────────────────────────


async def test_list_has_no_counters_when_nothing_is_registered(client):
    """No module above is a legitimate state: the card ships with no numbers, not with zeros."""
    await workspace_crud.workspace_create(title="Работа")

    body = (await client.get(BASE)).json()

    assert body[0]["counters"] == []


async def test_list_carries_a_registered_counter(client):
    """A module above declares the counter; the list only collects it — label key included."""
    row = await workspace_crud.workspace_create(title="Работа")

    async def count(codes: list[str]) -> dict[str, int]:
        return {code: 7 for code in codes}

    register_counter(
        WorkspaceCounter(key="notes", label_key="notes.workspace.counter", count_by_codes=count)
    )

    body = (await client.get(BASE)).json()

    assert body[0]["counters"] == [
        {"key": "notes", "label_key": "notes.workspace.counter", "count": 7}
    ]
    assert body[0]["code"] == f"WORKSPACE@{row.code}"


async def test_a_counter_that_skipped_a_workspace_reads_as_zero(client):
    """For the card, "not returned" and "found nothing" are one answer; the assembly fills in 0."""
    await workspace_crud.workspace_create(title="Пустое")

    async def count(codes: list[str]) -> dict[str, int]:
        return {}

    register_counter(
        WorkspaceCounter(key="notes", label_key="notes.workspace.counter", count_by_codes=count)
    )

    body = (await client.get(BASE)).json()

    assert body[0]["counters"][0]["count"] == 0


async def test_counters_follow_the_declared_order(client):
    """Registration sets the order (higher ``sort`` first), not whoever started up first."""
    await workspace_crud.workspace_create(title="Работа")

    async def count(codes: list[str]) -> dict[str, int]:
        return {code: 1 for code in codes}

    register_counter(
        WorkspaceCounter(key="later", label_key="a", count_by_codes=count, sort=100)
    )
    register_counter(
        WorkspaceCounter(key="earlier", label_key="b", count_by_codes=count, sort=900)
    )

    body = (await client.get(BASE)).json()

    assert [counter["key"] for counter in body[0]["counters"]] == ["earlier", "later"]


# ── create ────────────────────────────────────────────────────────────────────


async def test_create_returns_201_and_the_card(client):
    response = await client.post(
        BASE,
        json={"title": "Работа", "description": "о работе", "color": "teal", "icon": "folder"},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["title"] == "Работа"
    assert (body["color"], body["icon"]) == ("teal", "folder")
    assert body["deleted_at"] is None
    assert len(body["code"].removeprefix("WORKSPACE@")) == CODE_LEN


async def test_create_rejects_a_blank_title(client):
    """A whitespace-only name is rejected just like an empty one: a nameless card can't be found."""
    response = await client.post(BASE, json={"title": "   "})

    assert response.status_code == 422


async def test_create_rejects_an_overlong_title(client):
    response = await client.post(BASE, json={"title": "я" * (TITLE_MAX + 1)})

    assert response.status_code == 422


@pytest.mark.parametrize(("length", "status"), [(DESCRIPTION_MAX, 201), (DESCRIPTION_MAX + 1, 422)])
async def test_create_holds_the_description_limit(client, length, status):
    response = await client.post(BASE, json={"title": "Работа", "description": "я" * length})

    assert response.status_code == status
    assert len(await workspace_crud.workspace_list()) == (1 if status == 201 else 0)


async def test_create_rejects_an_unknown_field(client):
    """A typo in a field name is a refusal, not a silently ignored value (``extra=forbid``)."""
    response = await client.post(BASE, json={"title": "Работа", "colour": "teal"})

    assert response.status_code == 422


# ── read one ──────────────────────────────────────────────────────────────────


async def test_get_accepts_both_code_forms(client):
    """A person copies the prefixed code from the UI; modules pass the bare one to each other."""
    row = await workspace_crud.workspace_create(title="Работа")

    bare = await client.get(f"{BASE}/{row.code}")
    tagged = await client.get(f"{BASE}/WORKSPACE@{row.code}")

    assert bare.status_code == tagged.status_code == 200
    assert bare.json() == tagged.json()


async def test_get_returns_a_deleted_workspace_too(client):
    row = await workspace_crud.workspace_create(title="Работа")
    await workspace_crud.workspace_delete(row.code)

    body = (await client.get(f"{BASE}/{row.code}")).json()

    assert body["deleted_at"] is not None


async def test_get_of_a_missing_workspace_is_404(client):
    response = await client.get(f"{BASE}/{'0' * CODE_LEN}")

    assert response.status_code == 404
    assert response.json()["error"] == "Workspace not found"
    assert response.json()["code"] == "workspace.workspace.not_found"


async def test_a_foreign_code_prefix_is_a_bad_request(client):
    """A code of another type is a mixed-up argument, not a missing record: 400, not 404."""
    row = await workspace_crud.workspace_create(title="Работа")

    response = await client.get(f"{BASE}/AREA@{row.code}")

    assert response.status_code == 400


# ── update ────────────────────────────────────────────────────────────────────


async def test_update_replaces_the_card(client):
    row = await workspace_crud.workspace_create(
        title="Работа", description="о работе", icon="folder", color="teal"
    )

    body = (
        await client.put(
            f"{BASE}/{row.code}",
            json={"title": "Дело", "description": "", "color": "red", "icon": "rocket"},
        )
    ).json()

    assert body["title"] == "Дело"
    assert body["description"] == ""
    assert (body["color"], body["icon"]) == ("red", "rocket")


@pytest.mark.parametrize(("length", "status"), [(DESCRIPTION_MAX, 200), (DESCRIPTION_MAX + 1, 422)])
async def test_update_holds_the_description_limit(client, length, status):
    row = await workspace_crud.workspace_create(title="Работа", description="Старое")

    response = await client.put(
        f"{BASE}/{row.code}", json={"title": "Дело", "description": "я" * length}
    )

    assert response.status_code == status
    kept = await workspace_crud.workspace_get(row.code)
    expected = ("Дело", "я" * length) if status == 200 else ("Работа", "Старое")
    assert (kept.title, kept.description) == expected


async def test_update_of_a_deleted_workspace_is_a_conflict(client):
    row = await workspace_crud.workspace_create(title="Работа")
    await workspace_crud.workspace_delete(row.code)

    response = await client.put(f"{BASE}/{row.code}", json={"title": "Дело"})

    assert response.status_code == 409


async def test_update_of_a_missing_workspace_is_404(client):
    response = await client.put(f"{BASE}/{'0' * CODE_LEN}", json={"title": "Дело"})

    assert response.status_code == 404


# ── reorder ───────────────────────────────────────────────────────────────────


async def _codes() -> list[str]:
    return [row.code for row in await workspace_crud.workspace_list()]


async def test_reorder_puts_the_workspace_right_under_its_anchor(client):
    """The position is named by a neighbour: "under Работа" is a place, not a ``sort`` number."""
    first = await workspace_crud.workspace_create(title="Работа")
    second = await workspace_crud.workspace_create(title="Личное")
    third = await workspace_crud.workspace_create(title="Архив")

    response = await client.post(f"{BASE}/{third.code}/reorder", json={"after_code": first.code})

    assert response.status_code == 200
    assert response.json()["code"] == f"WORKSPACE@{third.code}"
    assert await _codes() == [first.code, third.code, second.code]


async def test_reorder_accepts_both_code_forms(client):
    """The moved one in the path and the neighbour in the body — prefixed as the list ships them."""
    first = await workspace_crud.workspace_create(title="Работа")
    second = await workspace_crud.workspace_create(title="Личное")

    response = await client.post(
        f"{BASE}/WORKSPACE@{second.code}/reorder",
        json={"before_code": f"WORKSPACE@{first.code}"},
    )

    assert response.status_code == 200
    assert await _codes() == [second.code, first.code]


async def test_reorder_folds_the_case_of_the_codes(client):
    first = await workspace_crud.workspace_create(title="Работа")
    second = await workspace_crud.workspace_create(title="Личное")

    response = await client.post(
        f"{BASE}/workspace@{second.code.lower()}/reorder",
        json={"before_code": f"workspace@{first.code.lower()}"},
    )

    assert response.status_code == 200
    assert await _codes() == [second.code, first.code]


@pytest.mark.parametrize("body", [{}, "both"], ids=["neither", "both"])
async def test_reorder_needs_exactly_one_reference_point(client, body):
    first = await workspace_crud.workspace_create(title="Работа")
    second = await workspace_crud.workspace_create(title="Личное")
    if body == "both":
        body = {"after_code": second.code, "before_code": second.code}

    response = await client.post(f"{BASE}/{first.code}/reorder", json=body)

    assert response.status_code == 400
    assert await _codes() == [first.code, second.code]


async def test_reorder_against_a_deleted_neighbour_is_400(client):
    first = await workspace_crud.workspace_create(title="Работа")
    gone = await workspace_crud.workspace_create(title="Удалённое")
    await workspace_crud.workspace_delete(gone.code)

    response = await client.post(f"{BASE}/{first.code}/reorder", json={"after_code": gone.code})

    assert response.status_code == 400


async def test_reorder_with_a_foreign_prefix_is_400(client):
    first = await workspace_crud.workspace_create(title="Работа")
    second = await workspace_crud.workspace_create(title="Личное")

    response = await client.post(
        f"{BASE}/{first.code}/reorder", json={"after_code": f"TASKGROUP@{second.code}"}
    )

    assert response.status_code == 400


async def test_reorder_rejects_an_unknown_field(client):
    first = await workspace_crud.workspace_create(title="Работа")

    response = await client.post(f"{BASE}/{first.code}/reorder", json={"sort": 900})

    assert response.status_code == 422


async def test_reorder_of_a_deleted_workspace_is_404(client):
    """A deleted one has no place in the list a person drags — the same answer as for a group."""
    gone = await workspace_crud.workspace_create(title="Удалённое")
    anchor = await workspace_crud.workspace_create(title="Работа")
    await workspace_crud.workspace_delete(gone.code)

    response = await client.post(f"{BASE}/{gone.code}/reorder", json={"after_code": anchor.code})

    assert response.status_code == 404


async def test_reorder_of_a_missing_workspace_is_404(client):
    anchor = await workspace_crud.workspace_create(title="Работа")

    response = await client.post(
        f"{BASE}/{'0' * CODE_LEN}/reorder", json={"after_code": anchor.code}
    )

    assert response.status_code == 404


# ── soft delete and restore ───────────────────────────────────────────────────


async def test_delete_is_soft(client):
    row = await workspace_crud.workspace_create(title="Работа")

    response = await client.delete(f"{BASE}/{row.code}")

    assert response.status_code == 204
    assert (await workspace_crud.workspace_get(row.code)) is None
    assert (await workspace_crud.workspace_get(row.code, include_deleted=True)) is not None


async def test_delete_of_a_missing_workspace_is_404(client):
    response = await client.delete(f"{BASE}/{'0' * CODE_LEN}")

    assert response.status_code == 404


async def test_restore_brings_the_workspace_back_to_the_list(client):
    row = await workspace_crud.workspace_create(title="Работа")
    await client.delete(f"{BASE}/{row.code}")

    restored = await client.post(f"{BASE}/{row.code}/restore")

    assert restored.status_code == 200
    assert restored.json()["deleted_at"] is None
    assert [item["title"] for item in (await client.get(BASE)).json()] == ["Работа"]


async def test_restore_of_a_live_workspace_is_a_conflict(client):
    row = await workspace_crud.workspace_create(title="Работа")

    response = await client.post(f"{BASE}/{row.code}/restore")

    assert response.status_code == 409


async def test_restore_of_a_missing_workspace_is_404(client):
    response = await client.post(f"{BASE}/{'0' * CODE_LEN}/restore")

    assert response.status_code == 404


# ── hard delete ───────────────────────────────────────────────────────────────


async def test_purge_removes_the_row(client):
    row = await workspace_crud.workspace_create(title="Работа")

    response = await client.delete(f"{BASE}/{row.code}/purge")

    assert response.status_code == 204
    assert (await workspace_crud.workspace_get(row.code, include_deleted=True)) is None


async def test_purge_works_on_a_softly_deleted_workspace(client):
    """The usual path from the UI: first to the trash, then "delete forever"."""
    row = await workspace_crud.workspace_create(title="Работа")
    await client.delete(f"{BASE}/{row.code}")

    response = await client.delete(f"{BASE}/{row.code}/purge")

    assert response.status_code == 204
    assert (await workspace_crud.workspace_get(row.code, include_deleted=True)) is None


async def test_purge_leaves_the_neighbours_alone(client):
    doomed = await workspace_crud.workspace_create(title="Под снос")
    kept = await workspace_crud.workspace_create(title="Остаётся")

    await client.delete(f"{BASE}/{doomed.code}/purge")

    assert (await workspace_crud.workspace_get(kept.code)) is not None


async def test_purge_of_a_missing_workspace_is_404(client):
    response = await client.delete(f"{BASE}/{'0' * CODE_LEN}/purge")

    assert response.status_code == 404
