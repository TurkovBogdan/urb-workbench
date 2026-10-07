"""HTTP API of the ``workspace`` module (mounted at ``/internal/workspace`` — see ``module.py``).

One surface — the workspace itself: list, create, read, update, soft delete, restore and hard
delete. A human creates and edits it (it is their layout, not the product of the agent's work),
so the set of endpoints is complete.

**Two deletions are two separate endpoints, on purpose.** ``DELETE /workspace/{code}`` sets a
mark: the contents stay in place, the list hides it unless asked, and ``restore`` brings
everything back as it was. ``DELETE /workspace/{code}/purge`` removes the row physically, and
with it — by FK cascade — everything the modules above kept in this workspace. Hiding the second
behind a flag on the first would mean the irreversible differs from the reversible by one
character in the URL.

**Counters ride along with each list row but do not belong to this module.** What lives inside a
workspace is known to the modules above; they declare the counters (``stats.py``), and the list
only collects what was declared. So the set of numbers in the response depends on the
application's composition, and an empty list is a legitimate answer. Without them the delete
dialog would say "the contents will disappear" without saying how much — i.e. it would ask to
confirm something unknown.

**An unknown field in the body is a refusal, not silence** (``_Body`` with ``extra="forbid"``):
otherwise a typo in a field name slips through silently and yields 201 with a card lacking that
value.

**A code is accepted on input in both forms** — ``WORKSPACE@<hash>`` and the bare hash: a human
copies the first from the interface, modules pass the second to each other internally. The code
prefix is named after the entity, and renaming the module does not affect it. A foreign prefix
(``TASKGROUP@``) is not "not found" but a mixed-up argument, so we answer it with 400, not a 404
that would lead to thinking the record was deleted.

The ``internal`` zone in the bare core is open (``allow_all``); no guard needed.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query, Response
from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from src.core.api import ApiError
from src.modules.workspace import stats
from src.modules.workspace.codes import bare_code
from src.modules.workspace.constants import (
    COLOR_MAX,
    DESCRIPTION_MAX,
    ICON_MAX,
    SORT_DEFAULT,
    TITLE_MAX,
    WORKSPACE_CODE_PREFIX,
)
from src.modules.workspace.crud import workspace as workspace_crud
from src.modules.workspace.errors import WORKSPACE_DELETED, WORKSPACE_NOT_DELETED, WORKSPACE_NOT_FOUND
from src.modules.workspace.dto import (
    WorkspaceCounterRow,
    WorkspaceListRow,
    WorkspaceRow,
)
from src.modules.workspace.models.workspace import Workspace

router = APIRouter()


class _Body(BaseModel):
    """The common ancestor of all request bodies: an unknown field is a refusal, not silence.

    ``extra="forbid"`` sits here rather than on each model, precisely so that a new endpoint
    cannot be introduced without it. On response DTOs (``dto.py``) the ban is unnecessary and
    harmful: we build those ourselves, and ``from_attributes`` reads an ORM row's attributes,
    where nothing extra ever appears.
    """

    model_config = ConfigDict(extra="forbid")


class WorkspaceBody(_Body):
    """The body for creating and editing a workspace — one field set for both endpoints.

    Surrounding whitespace in the title is stripped BEFORE the length check, so a title of only
    spaces is rejected just like an empty one: a workspace without a title is indistinguishable
    in the list, and "erase the title" is not a scenario. The description may be empty: it is
    optional.

    Colour and icon names are not checked against the palettes — for the same reason the DB does
    not check them: only the frontend knows how to draw them, and it also survives an unknown
    name, while a check here would turn extending a palette into editing two files in two
    languages.

    ``sort`` is the position in the list, higher goes first — as for a task group. It has a
    default, so a form that does not care about order may omit it.
    """

    title: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=TITLE_MAX)
    ]
    description: Annotated[
        str, StringConstraints(strip_whitespace=True, max_length=DESCRIPTION_MAX)
    ] = ""
    color: str = Field(default="", max_length=COLOR_MAX)
    icon: str = Field(default="", max_length=ICON_MAX)
    sort: int = SORT_DEFAULT


class WorkspaceReorderBody(_Body):
    """One drag of a row: the workspace it now stands next to.

    Exactly one of the two reference points, as for a task group: both at once would contradict
    each other, neither would mean "put it somewhere" — either way 400, not a choice made for the
    caller. No position number: ``sort`` is layout mechanics the mouse cannot aim at.
    """

    after_code: str | None = None
    before_code: str | None = None


def _code(value: str) -> str:
    """The bare workspace code from a path segment; a foreign type is 400, not 404.

    ``bare_code`` tells "a code of another entity" from "no such code": the first is fixed by
    correcting the call, the second is not, and mixing them up in the response sends the client
    looking for a loss that never happened.
    """
    try:
        return bare_code(value, WORKSPACE_CODE_PREFIX) or ""
    except ValueError as error:
        raise ApiError.bad_request(str(error)) from error


def _optional_code(value: str | None) -> str | None:
    """A neighbour's code from a body field: absent stays absent, a foreign type is 400."""
    return None if value is None else _code(value)


async def _require(code: str) -> Workspace:
    """A workspace in any state, or 404.

    A deleted one is looked up on a par with a live one (``include_deleted=True``): it is shown in
    the list, restored and purged — for all three scenarios "not found" would mean the endpoint
    does not see what the human sees on screen right now.
    """
    row = await workspace_crud.workspace_get(code, include_deleted=True)
    if row is None:
        raise ApiError.not_found("Workspace not found", code=WORKSPACE_NOT_FOUND)
    return row


@router.get("")
async def list_workspaces(
    include_deleted: bool = Query(
        False, description="Also show deleted workspaces (marked with ``deleted_at``)"
    ),
) -> list[WorkspaceListRow]:
    """Workspaces top to bottom (``sort``, then title) + the counters declared by the modules above.

    No pagination on purpose: a workspace is the top level of the layout, they are created one at
    a time, and paging here would be an organ with nothing to page through.
    """
    rows = await workspace_crud.workspace_list(include_deleted=include_deleted)
    codes = [row.code for row in rows]
    counted = await stats.counts_for(codes)
    specs = stats.registered_counters()
    return [
        WorkspaceListRow(
            **WorkspaceRow.model_validate(row).model_dump(),
            counters=[
                WorkspaceCounterRow(
                    key=spec.key,
                    label_key=spec.label_key,
                    count=counted[row.code][spec.key],
                )
                for spec in specs
            ],
        )
        for row in rows
    ]


@router.post("", status_code=201)
async def create_workspace(payload: WorkspaceBody) -> WorkspaceRow:
    row = await workspace_crud.workspace_create(
        title=payload.title,
        description=payload.description,
        color=payload.color,
        icon=payload.icon,
        sort=payload.sort,
    )
    return WorkspaceRow.model_validate(row)


@router.get("/{code}")
async def get_workspace(code: str) -> WorkspaceRow:
    """One workspace — including a deleted one: its state shows in ``deleted_at``."""
    return WorkspaceRow.model_validate(await _require(_code(code)))


@router.put("/{code}")
async def update_workspace(code: str, payload: WorkspaceBody) -> WorkspaceRow:
    """A full replacement of the card: the body carries every field, an empty value erases its
    own, and a missing ``sort`` puts the default position back.

    A deleted one is not editable — ``restore`` first. We answer 409, not 404: the record exists
    and the human sees it in the deleted list; this operation just does not apply to it now.
    """
    bare = _code(code)
    existing = await _require(bare)
    if existing.deleted_at is not None:
        raise ApiError.conflict("Workspace is deleted — restore it first", code=WORKSPACE_DELETED)
    row = await workspace_crud.workspace_update(
        bare,
        title=payload.title,
        description=payload.description,
        color=payload.color,
        icon=payload.icon,
        sort=payload.sort,
    )
    if row is None:
        raise ApiError.not_found("Workspace not found", code=WORKSPACE_NOT_FOUND)
    return WorkspaceRow.model_validate(row)


@router.post("/{code}/reorder")
async def reorder_workspace(code: str, payload: WorkspaceReorderBody) -> WorkspaceRow:
    """Move a workspace relative to another one — this is how the list is rearranged by dragging.

    The position is named by a neighbour, not a number; CRUD renumbers the list itself.
    """
    bare = _code(code)
    await _require(bare)
    try:
        row = await workspace_crud.workspace_reorder(
            bare,
            after=_optional_code(payload.after_code),
            before=_optional_code(payload.before_code),
        )
    except ValueError as error:
        # "Pass exactly one reference point" and "no such neighbour" are both fixed by correcting
        # the call, not by hunting for a loss — hence 400, not 404.
        raise ApiError.bad_request(str(error)) from error
    if row is None:
        raise ApiError.not_found("Workspace not found", code=WORKSPACE_NOT_FOUND)
    return WorkspaceRow.model_validate(row)


@router.delete("/{code}", status_code=204)
async def delete_workspace(code: str) -> Response:
    """Soft delete: the contents stay, and the list hides it unless asked.

    Deleting an already deleted one again is not an error: the CRUD leaves a marked row alone,
    and the outcome matches the intent — the workspace is deleted.
    """
    if not await workspace_crud.workspace_delete(_code(code)):
        raise ApiError.not_found("Workspace not found", code=WORKSPACE_NOT_FOUND)
    return Response(status_code=204)


@router.post("/{code}/restore")
async def restore_workspace(code: str) -> WorkspaceRow:
    """Clear the deletion mark and return the card — the list shows it right away.

    A live workspace cannot be restored: that is not "already fine" but a sign the button was
    pressed on the wrong row (say, the list had refreshed in between), and a silent "ok" would
    hide the mismatch between what is on screen and what is in the database.
    """
    bare = _code(code)
    existing = await _require(bare)
    if existing.deleted_at is None:
        raise ApiError.conflict("Workspace is not deleted — nothing to restore", code=WORKSPACE_NOT_DELETED)
    await workspace_crud.workspace_restore(bare)
    return WorkspaceRow.model_validate(await _require(bare))


@router.delete("/{code}/purge", status_code=204)
async def purge_workspace(code: str) -> Response:
    """Hard delete: the row leaves the table, and the FK cascade takes the modules' contents with it.

    A separate URL, not a flag on the soft delete: the difference between "can be brought back"
    and "nothing to bring back" must not hide in a query parameter that is easy to lose when
    copying a call. No timestamp remains afterwards — there is nothing to restore and nowhere
    to restore it from.
    """
    if not await workspace_crud.workspace_delete(_code(code), hard=True):
        raise ApiError.not_found("Workspace not found", code=WORKSPACE_NOT_FOUND)
    return Response(status_code=204)


__all__ = ["router"]
