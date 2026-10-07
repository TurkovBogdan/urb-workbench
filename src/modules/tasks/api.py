"""HTTP API of the ``tasks`` module (mounted at ``/internal/workbench`` — see ``module.py``).

Two surfaces: **groups** (long-lived topics inside a workspace) and **tasks**. The workspace
itself lives in the module one level down (``workspace``) and has its API there — here its code
is only accepted as a parameter and checked.

No query crosses workspaces — which is why ``workspace`` is required on the group and task lists:
without it "all tasks" would mean work and personal mixed in one response.

Groups and tasks get the full set of endpoints: list, create, read, update, soft delete, restore
and hard delete — with one difference: a group's workspace is set at creation and cannot be
changed by an update, because moving a group would drag all its tasks along.

**Task status changes through a separate endpoint** (``POST /tasks/{code}/status``); the general
update does not accept it. A status transition is not writing a value into a column: it stamps a
phase mark (start, completion, cancellation), and ``task_update_status`` is what stamps it. Allow
status in the general update and a second change path would appear next to it with nobody to
stamp the mark — and "done" without ``completed_at`` could no longer be explained by anything.

**A task's place in the tree rides in the task's own row** (``parent_code`` / ``sort``), even
though it lives in a separate table: the split serves writes (moving a branch does not rewrite
the card), while a reading list needs both halves at once. They are also changed by a separate
endpoint — ``move``: moving is an operation on the tree, not an edit of a card field.

**Two deletions — two different endpoints, on purpose.** ``DELETE /groups/{code}`` (same for a
task) sets a mark: the content stays in place, the list hides it without the flag, ``restore``
brings everything back as it was. ``DELETE /groups/{code}/purge`` removes the row physically.
Hiding the second behind a flag of the first would make the irreversible differ from the
reversible by one character in the URL.

**Workspace content counters are declared from here**, not queried from there: the workspace card
needs "how many groups and tasks inside", but the module one level down cannot know about groups
and tasks. We register them in its registry (``workspace.stats``) in ``module.py``.

**An unknown field in the body is a refusal, not silence.** Every input model sits on
``extra="forbid"`` (``_Body``): a typo in a field name used to pass silently — ``parent`` instead
of ``parent_code`` gave 201 and a task without a parent, and the only way to find out was that the
task did not land in its branch. Now such a request answers 422 with ``fields``, keyed by the
extra name itself.

**Input codes are accepted in both forms** — ``WORKSPACE@<hash>`` and the bare hash: the person
copies the first from the UI, the module hands out the second internally. A foreign prefix
(``TASKGROUP@`` instead of ``WORKSPACE@``) is not "not found" but a mixed-up argument, and we
answer it with 400 naming both types, not with a 404 that would suggest the record was deleted.

The ``internal`` zone is open in the bare core (``allow_all``), no guard needed.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Query, Response
from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from src.core.api import ApiError
from src.modules.tasks.codes import bare_code, tagged
from src.modules.tasks.constants import (
    COLOR_MAX,
    DESCRIPTION_MAX,
    GROUP_CODE_PREFIX,
    GROUP_DESCRIPTION_MAX,
    GROUP_TASK_DISPOSALS,
    ICON_MAX,
    NOTE_CODE_PREFIX,
    SORT_DEFAULT,
    STAGE_CODE_PREFIX,
    TASK_CODE_PREFIX,
    TASK_PRIORITY_DEFAULT,
    TASK_STATUS_DEFAULT,
    TASK_TYPE_DEFAULT,
    TITLE_MAX,
)
from src.modules.tasks.crud import group as group_crud
from src.modules.tasks.crud import link as link_crud
from src.modules.tasks.crud import note as note_crud
from src.modules.tasks.crud import stage as stage_crud
from src.modules.tasks.crud import task as task_crud
from src.modules.tasks.errors import (
    GROUP_DELETED,
    GROUP_NOT_DELETED,
    GROUP_NOT_FOUND,
    NOTE_NOT_FOUND,
    STAGE_NOT_FOUND,
    TASK_DELETED,
    TASK_NOT_DELETED,
    TASK_NOT_FOUND,
    TaskRuleError,
)
from src.modules.tasks.dto import (
    GroupListRow,
    GroupRow,
    NoteRow,
    StageRow,
    TaskDetail,
    TaskListRow,
    TaskRow,
)
from src.modules.tasks.models.task import TasksTask
from src.modules.workspace.constants import WORKSPACE_CODE_PREFIX
from src.modules.workspace.crud import workspace as workspace_crud
from src.modules.workspace.errors import WORKSPACE_NOT_FOUND
from src.modules.workspace.models.workspace import Workspace

router = APIRouter()


class _Body(BaseModel):
    """Common ancestor of every request body: an unknown field is a refusal, not silence.

    ``extra="forbid"`` sits here rather than on each model, precisely so a new endpoint cannot
    be born without it: silently ignoring an extra field is the most expensive of the small
    contract bugs. A ``parent`` sent instead of ``parent_code`` answered 201 and created a task
    without a parent; the difference showed only in the task not landing in its branch.

    On response DTOs (``dto.py``) the ban is unnecessary and harmful: we build them ourselves,
    and ``from_attributes`` reads attributes of an ORM row, which never has extras.
    """

    model_config = ConfigDict(extra="forbid")


def _bare(value: str | None, prefix: str) -> str | None:
    """Bare code of the expected type; a foreign type is 400, not 404.

    ``bare_code`` tells "a code of another entity" from "no code": the first is fixed by
    correcting the call, the second is not, and mixing them up in the response sends the client
    hunting for a loss that never happened.
    """
    try:
        return bare_code(value, prefix)
    except ValueError as error:
        raise ApiError.bad_request(str(error)) from error


def _code(value: str) -> str:
    """Bare workspace code from a path segment or from the ``workspace`` parameter."""
    return _bare(value, WORKSPACE_CODE_PREFIX) or ""


def _task_code(value: str) -> str:
    """Bare task code from a path segment."""
    return _bare(value, TASK_CODE_PREFIX) or ""


async def _require_workspace(code: str) -> Workspace:
    """A live or deleted workspace — or 404.

    The workspace belongs to the module one level down (``workspace``), so we ask through its
    own CRUD rather than with our own query against someone else's table: we hold an FK to it,
    but not the right to decide what "exists" means for another module's entity.

    A deleted one is looked up on par with a live one (``include_deleted=True``): groups and
    tasks of a deleted workspace are shown in the UI, and "not found" would mean the endpoint
    cannot see what the person is looking at on screen right now.
    """
    row = await workspace_crud.workspace_get(code, include_deleted=True)
    if row is None:
        raise ApiError.not_found("Workspace not found", code=WORKSPACE_NOT_FOUND)
    return row


# ── groups ────────────────────────────────────────────────────────────────────


class GroupBody(_Body):
    """Body for creating and updating a group — one field set for both endpoints.

    The workspace is absent on purpose: on create it comes as a query parameter (the group is
    created INSIDE it), and an update cannot change it at all — moving a group would drag all its
    tasks along, and that is a different operation.

    ``sort`` is the position among siblings, higher goes first. It has a default, so a form that
    does not care about order may omit it.
    """

    title: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=TITLE_MAX)
    ]
    description: Annotated[
        str, StringConstraints(strip_whitespace=True, max_length=GROUP_DESCRIPTION_MAX)
    ] = ""
    color: str = Field(default="", max_length=COLOR_MAX)
    icon: str = Field(default="", max_length=ICON_MAX)
    sort: int = SORT_DEFAULT


def _group_code(value: str) -> str:
    """Bare group code from a path segment."""
    return _bare(value, GROUP_CODE_PREFIX) or ""


async def _require_group(code: str):
    """A group in any state, or 404 — for the same reason as the workspace."""
    row = await group_crud.group_get(code, include_deleted=True)
    if row is None:
        raise ApiError.not_found("Group not found", code=GROUP_NOT_FOUND)
    return row


@router.get("/groups")
async def list_groups(
    workspace: str = Query(..., description="Workspace code (``WORKSPACE@…`` or bare)"),
    include_deleted: bool = Query(False, description="Include deleted groups too"),
) -> list[GroupListRow]:
    """A workspace's groups top to bottom + how many live tasks each holds.

    The workspace is required: a group does not exist outside one, and "all groups" would mix
    the layouts of different workspaces into one list where identical titles ("Interface")
    cannot be told apart.
    """
    bare = _code(workspace)
    await _require_workspace(bare)
    rows = await group_crud.group_list_by_workspace(bare, include_deleted=include_deleted)
    tasks = await task_crud.task_count_by_group_codes([row.code for row in rows])
    return [
        GroupListRow(
            **GroupRow.model_validate(row).model_dump(),
            task_count=tasks.get(row.code, 0),
        )
        for row in rows
    ]


@router.post("/groups", status_code=201)
async def create_group(
    payload: GroupBody,
    workspace: str = Query(..., description="Code of the workspace the group is created in"),
) -> GroupRow:
    """Create a group in a workspace. A dead workspace is refused, and the refusal text is CRUD's."""
    bare = _code(workspace)
    await _require_workspace(bare)
    try:
        row = await group_crud.group_create(
            workspace_code=bare,
            title=payload.title,
            description=payload.description,
            color=payload.color,
            icon=payload.icon,
            sort=payload.sort,
        )
    except ValueError as error:
        raise ApiError.conflict(str(error)) from error
    return GroupRow.model_validate(row)


@router.get("/groups/{code}")
async def get_group(code: str) -> GroupRow:
    """One group — deleted ones included: its state shows in ``deleted_at``."""
    return GroupRow.model_validate(await _require_group(_group_code(code)))


@router.put("/groups/{code}")
async def update_group(code: str, payload: GroupBody) -> GroupRow:
    """Full replacement of a group card; a deleted one is not editable — ``restore`` first (409)."""
    bare = _group_code(code)
    existing = await _require_group(bare)
    if existing.deleted_at is not None:
        raise ApiError.conflict("Group is deleted — restore it first", code=GROUP_DELETED)
    row = await group_crud.group_update(
        bare,
        title=payload.title,
        description=payload.description,
        color=payload.color,
        icon=payload.icon,
        sort=payload.sort,
    )
    if row is None:
        raise ApiError.not_found("Group not found", code=GROUP_NOT_FOUND)
    return GroupRow.model_validate(row)


@router.post("/groups/{code}/reorder")
async def reorder_group(code: str, payload: GroupReorderBody) -> GroupRow:
    """Move a group relative to a sibling — this is how the layout is rearranged with the mouse.

    The position is named by a sibling, not a number: the screen shows which cards the group
    landed between, while its ``sort`` is not visible at all. CRUD renumbers the siblings itself.
    """
    bare = _group_code(code)
    await _require_group(bare)
    try:
        row = await group_crud.group_reorder(
            bare,
            after=_bare(payload.after_code, GROUP_CODE_PREFIX),
            before=_bare(payload.before_code, GROUP_CODE_PREFIX),
        )
    except ValueError as error:
        # Both "pass exactly one reference point" and "sibling from another workspace" land here:
        # all of it is fixed by correcting the call, not by hunting for a loss — hence 400, not 404.
        raise ApiError.bad_request(str(error)) from error
    if row is None:
        raise ApiError.not_found("Group not found", code=GROUP_NOT_FOUND)
    return GroupRow.model_validate(row)


@router.delete("/groups/{code}", status_code=204)
async def delete_group(
    code: str,
    tasks: str | None = Query(
        None, description="ungroup / move / delete — required while the group holds live tasks"
    ),
    target: str | None = Query(None, description="The group to move the tasks to (``move``)"),
) -> Response:
    """Soft delete, together with the fate of the group's tasks — one transaction.

    No task is left pointing at a deleted group: nothing draws one, and its tasks would vanish
    from the list. A group with live tasks and no ``tasks`` is 409 (``tasks.group.has_tasks``);
    a bad ``target`` is 400. ``restore`` later brings back the group alone.
    """
    if tasks is not None and tasks not in GROUP_TASK_DISPOSALS:
        raise ApiError.bad_request(f"tasks must be one of: {', '.join(GROUP_TASK_DISPOSALS)}")
    try:
        deleted = await group_crud.group_delete(
            _group_code(code), tasks=tasks, target=_bare(target, GROUP_CODE_PREFIX)
        )
    except TaskRuleError as error:
        raise ApiError.conflict(str(error), code=error.code) from error
    except ValueError as error:
        raise ApiError.bad_request(str(error)) from error
    if not deleted:
        raise ApiError.not_found("Group not found", code=GROUP_NOT_FOUND)
    return Response(status_code=204)


@router.post("/groups/{code}/restore")
async def restore_group(code: str) -> GroupRow:
    """Clear the deletion mark. A live group cannot be restored — 409, same as a workspace."""
    bare = _group_code(code)
    existing = await _require_group(bare)
    if existing.deleted_at is None:
        raise ApiError.conflict("Group is not deleted — nothing to restore", code=GROUP_NOT_DELETED)
    await group_crud.group_restore(bare)
    return GroupRow.model_validate(await _require_group(bare))


@router.delete("/groups/{code}/purge", status_code=204)
async def purge_group(code: str) -> Response:
    """Hard delete of a group. Its tasks outlive it: the FK ``SET NULL`` ungroups them.

    So purging a group is not purging the work: the tasks move to the "No group" section, not to
    the trash.
    """
    if not await group_crud.group_delete(_group_code(code), hard=True):
        raise ApiError.not_found("Group not found", code=GROUP_NOT_FOUND)
    return Response(status_code=204)


# ── tasks ─────────────────────────────────────────────────────────────────────


class TaskCreateBody(_Body):
    """Body for creating a task: only the workspace and the title are required.

    Everything else has a column-level default (``backlog`` / ``normal`` / ``simple``), so
    requiring it on input would force the client to repeat what the module already knows.
    Reference values are not checked here — CRUD does that, and its refusal lists the allowed
    ones; a second copy of the enums in the API would drift from it at the very first new status.

    The body has no ``created_by``: the author is named by the surface, not the client. This one
    is the person's (the UI calls it), and any value from here would be taken on faith.
    """

    workspace: str
    title: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=TITLE_MAX)
    ]
    description: Annotated[
        str, StringConstraints(strip_whitespace=True, max_length=DESCRIPTION_MAX)
    ] = ""
    context: str = ""
    constraints: str = ""
    criteria: str = ""
    body: str = ""
    type: str = TASK_TYPE_DEFAULT
    status: str = TASK_STATUS_DEFAULT
    priority: str = TASK_PRIORITY_DEFAULT
    group_code: str | None = None
    parent_code: str | None = None
    deadline_at: datetime | None = None


class TaskUpdateBody(_Body):
    """Body for updating a task — full replacement of the card: an omitted field is erased.

    Replacement rather than "fix what is named", for the same reason as with the workspace: the UI
    form always sends the whole card, so the only way to clear a deadline or a group is the absence
    of a value. Allow partial updates and "erase" and "leave alone" would become
    indistinguishable, and a deadline once set could never be cleared.

    There is no status here — see ``POST /tasks/{code}/status``.
    """

    title: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=TITLE_MAX)
    ]
    description: Annotated[
        str, StringConstraints(strip_whitespace=True, max_length=DESCRIPTION_MAX)
    ] = ""
    context: str = ""
    constraints: str = ""
    criteria: str = ""
    body: str = ""
    type: str = TASK_TYPE_DEFAULT
    priority: str = TASK_PRIORITY_DEFAULT
    group_code: str | None = None
    deadline_at: datetime | None = None


class TaskPatchBody(_Body):
    """Partial update of the card: only the fields sent change, the rest are left alone.

    The task page needs it: it saves a field as soon as focus leaves it. A full replacement
    (``TaskUpdateBody``) would send every other field along with it as the page once loaded them
    — and roll back whatever the agent wrote in the meantime.

    "Not sent" and ``null`` are told apart by ``model_fields_set``: for the group and the deadline
    ``null`` means "clear", while a missing key means "leave alone". Text fields do not accept
    ``null`` — "empty" for them is the empty string.
    """

    title: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=TITLE_MAX)
    ] | None = None
    description: Annotated[
        str, StringConstraints(strip_whitespace=True, max_length=DESCRIPTION_MAX)
    ] | None = None
    context: str | None = None
    constraints: str | None = None
    criteria: str | None = None
    body: str | None = None
    type: str | None = None
    priority: str | None = None
    group_code: str | None = None
    deadline_at: datetime | None = None


class TaskStatusBody(_Body):
    """One status and nothing else: a transition has no other parameters."""

    status: str


class TaskMoveBody(_Body):
    """The task's new place in the tree: under whom and at what position.

    An empty ``parent_code`` is the workspace root, not "keep the parent": a move always names
    the whole place, and "leave as is" is expressed by not calling the endpoint. ``sort`` without
    a value puts the task at the end of its new siblings — the most common case ("move it
    there"), for which nobody wants to compute positions on the client.
    """

    parent_code: str | None = None
    sort: int | None = None


class GroupReorderBody(_Body):
    """One group drag: the sibling it now sits next to.

    Exactly one of the two reference points — same as in CRUD. Both at once would contradict each
    other, and neither would mean "put it somewhere"; either way the answer is 400, not a silent
    choice made for the caller.

    There is no position number on purpose: ``sort`` is internal layout mechanics, and whoever
    drags a card with the mouse has no way to hit it.
    """

    after_code: str | None = None
    before_code: str | None = None


class TaskReorderBody(_Body):
    """One drag: where the row now stands, which group it is in and whose child it is.

    ``after_code`` is the task the moved one landed AFTER (empty — first among its siblings). The
    position is named by a sibling, not a number: the on-screen list has its own filters and
    pages, and a row number there does not match the number among siblings in the database.

    ``group_code`` absent from the body — the group is left alone; ``null`` — clear the group.
    The difference is read from ``model_fields_set``: a drag within one group must know nothing
    about groups, while a drag into "No group" must be able to clear it, and a single ``None``
    cannot tell the two cases apart.

    ``parent_code`` works the same way: no key — the parent is left alone, ``null`` — detach,
    i.e. make the task a root. This is the list's second gesture: a subtask is pulled out of its
    branch onto a group card and stops being a subtask.
    """

    after_code: str | None = None
    group_code: str | None = None
    parent_code: str | None = None


async def _require_task(code: str) -> TasksTask:
    """A task in any state, or 404.

    A deleted one is looked up on par with a live one: the list shows it under a flag, it gets
    restored and purged — in all three scenarios "not found" would mean the endpoint cannot see
    what the person is looking at on screen right now.
    """
    row = await task_crud.task_get(code, include_deleted=True)
    if row is None:
        raise ApiError.not_found("Task not found", code=TASK_NOT_FOUND)
    return row


def _live(row: TasksTask) -> None:
    """Card operations are forbidden while the task is in the trash: ``restore`` first.

    409, not 404: the record exists and the person sees it in the deleted list — this operation
    just does not apply to it right now.
    """
    if row.deleted_at is not None:
        raise ApiError.conflict("Task is deleted — restore it first", code=TASK_DELETED)


async def _rows(rows: list[TasksTask], *, include_deleted: bool) -> list[TaskListRow]:
    """Tasks + their edges + a branch flag — in tree order (higher ``sort`` first).

    The two mixed-in values are fetched with one query each (``link_map_by_task_codes`` and
    ``link_child_count_by_parent_codes``), not one query per card: a workspace list fits on the
    screen whole, and N+1 here would cost exactly as many lines of code as it saves.

    Ordering happens here, not in CRUD: ``task_list_by_workspace`` sorts by importance (the
    answer to "what to pick up"), while the list needs branch order — the one the person arranged
    by hand. Different questions to the same table, and the second kind of sort is assembling
    the response, not a different query.
    """
    codes = [row.code for row in rows]
    links = await link_crud.link_map_by_task_codes(codes)
    children = await link_crud.link_child_count_by_parent_codes(
        codes, include_deleted=include_deleted
    )
    built = []
    for row in rows:
        link = links.get(row.code)
        built.append(
            TaskListRow(
                **TaskRow.model_validate(row).model_dump(),
                parent_code=link.parent_code if link else None,
                sort=link.sort if link else SORT_DEFAULT,
                has_children=children.get(row.code, 0) > 0,
            )
        )
    built.sort(key=lambda item: (-item.sort, item.created_at, item.code))
    return built


async def _detail(row: TasksTask) -> TaskDetail:
    """The whole task: its fields, body, edge, group, parent and children.

    Children of a deleted task are fetched including deleted ones: soft delete cascades, and a
    task in the trash has no live children left — showing an empty list would lie that the
    branch under it is empty, and the person looks at it precisely before deciding whether to
    restore or purge.

    The group and the parent are also looked up including deleted ones: a deleted group is not
    cleared from the task (see ``group_delete``), and showing "No group" where the grouping is
    actually intact would lie about what comes back once the group is restored.
    """
    deleted = row.deleted_at is not None
    link = await link_crud.link_get(row.code)
    children = await task_crud.task_list_by_parent(row.code, include_deleted=deleted)
    group = (
        await group_crud.group_get(row.group_code, include_deleted=True)
        if row.group_code
        else None
    )
    parent = (
        await task_crud.task_get(link.parent_code, include_deleted=True)
        if link and link.parent_code
        else None
    )
    parent_rows = await _rows([parent], include_deleted=True) if parent else []
    stages = await stage_crud.stage_list_by_task(row.code)
    notes = await note_crud.note_list_by_task(row.code)
    return TaskDetail(
        **TaskRow.model_validate(row).model_dump(),
        context=row.context,
        constraints=row.constraints,
        criteria=row.criteria,
        body=row.body,
        parent_code=link.parent_code if link else None,
        sort=link.sort if link else SORT_DEFAULT,
        has_children=bool(children),
        group=GroupRow.model_validate(group) if group else None,
        parent=parent_rows[0] if parent_rows else None,
        children=await _rows(children, include_deleted=deleted),
        stages=[StageRow.model_validate(stage) for stage in stages],
        notes=[NoteRow.model_validate(note) for note in notes],
    )


@router.get("/tasks")
async def list_tasks(
    workspace: str = Query(..., description="Workspace code (``WORKSPACE@…`` or bare)"),
    include_deleted: bool = Query(False, description="Include deleted tasks too"),
    status: str | None = Query(None, description="Only tasks in this status"),
    group: str | None = Query(
        None,
        description="Only tasks of this group; an empty value means only ungrouped tasks",
    ),
) -> list[TaskListRow]:
    """A flat list of the workspace's tasks — the tree edges ride along in it.

    Flat, because the client lays it out: its sections are by group, not by nesting level, and a
    tree assembled on the backend would have to be taken apart again. Parent and position are in
    every row — enough to build any layout, nested included.

    An empty ``group`` is not "no filter" but "ungrouped only": the list has a "No group" section,
    and there is no other way to ask about it. "No filter" is the parameter's absence.
    """
    bare = _code(workspace)
    await _require_workspace(bare)
    try:
        rows = await task_crud.task_list_by_workspace(
            bare,
            status=status,
            group_code=_bare(group, GROUP_CODE_PREFIX),
            include_deleted=include_deleted,
        )
    except ValueError as error:
        raise ApiError.bad_request(str(error)) from error
    return await _rows(rows, include_deleted=include_deleted)


@router.get("/tasks/search")
async def search_tasks(
    workspace: str = Query(..., description="Workspace code (``WORKSPACE@…`` or bare)"),
    query: str = Query(..., description="What to search for — a case-insensitive substring"),
    in_brief: bool = Query(False, description="Search the brief: context, constraints, criteria"),
    in_plan: bool = Query(False, description="Search the task plan and its stage bodies"),
    in_journal: bool = Query(False, description="Search journal entries"),
) -> list[str]:
    """Codes of tasks whose bodies contain the query — in the named areas.

    This is the second half of list search, not a replacement for it: the title and goal are in
    every row, and the client searches those itself — instantly, with no network round trip. It
    comes here only for what the row lacks and intersects the answer with its own list. Hence
    codes are returned: the caller already has the cards.

    Declared ABOVE ``GET /tasks/{code}``: routes are matched in declaration order, and below it
    this URL would fall into the detail of a task coded ``search``.
    """
    bare = _code(workspace)
    await _require_workspace(bare)
    found = await task_crud.task_search_codes(
        bare,
        query,
        in_brief=in_brief,
        in_plan=in_plan,
        in_journal=in_journal,
    )
    # Codes go out in the same form the list carries them (``TASK@…``): that list is what they
    # get intersected with, and two forms of one code would silently give an empty intersection.
    return [tagged(TASK_CODE_PREFIX, code) for code in found]


@router.post("/tasks", status_code=201)
async def create_task(payload: TaskCreateBody) -> TaskDetail:
    """Create a task (together with its tree edge) and return it whole.

    We answer with the detail, not a list row: creating from a parent's card immediately opens
    the new task, and a second request for what we just wrote would be a wasted round trip.
    """
    try:
        row = await task_crud.task_create(
            workspace_code=_code(payload.workspace),
            title=payload.title,
            description=payload.description,
            context=payload.context,
            constraints=payload.constraints,
            criteria=payload.criteria,
            body=payload.body,
            type=payload.type,
            status=payload.status,
            priority=payload.priority,
            group_code=_bare(payload.group_code, GROUP_CODE_PREFIX),
            parent_code=_bare(payload.parent_code, TASK_CODE_PREFIX),
            deadline_at=payload.deadline_at,
        )
    except ValueError as error:
        # A ValueError here is a nonexistent workspace, a foreign group, a foreign parent or a
        # value outside the reference set. All of it is fixed by correcting the call, hence 400
        # with CRUD's text (it also names the allowed values), not 404: what was asked for did not
        # "go missing", it cannot exist.
        raise ApiError.bad_request(str(error)) from error
    return await _detail(row)


@router.get("/tasks/{code}")
async def get_task(code: str) -> TaskDetail:
    """One task — deleted ones included: its state shows in ``deleted_at``."""
    return await _detail(await _require_task(_task_code(code)))


@router.put("/tasks/{code}")
async def update_task(code: str, payload: TaskUpdateBody) -> TaskDetail:
    """Full card replacement. Status and tree place are excluded — each has its own endpoint."""
    bare = _task_code(code)
    _live(await _require_task(bare))
    try:
        row = await task_crud.task_update(
            bare,
            title=payload.title,
            description=payload.description,
            context=payload.context,
            constraints=payload.constraints,
            criteria=payload.criteria,
            body=payload.body,
            type=payload.type,
            priority=payload.priority,
            # An empty string is CRUD's only form of "no group": ``None`` there means "leave
            # alone", and a card update must be able to ungroup.
            group_code=_bare(payload.group_code, GROUP_CODE_PREFIX) or "",
            deadline_at=payload.deadline_at,
        )
    except ValueError as error:
        raise ApiError.bad_request(str(error)) from error
    if row is None:
        raise ApiError.not_found("Task not found", code=TASK_NOT_FOUND)
    return await _detail(row)


@router.patch("/tasks/{code}")
async def patch_task(code: str, payload: TaskPatchBody) -> TaskDetail:
    """Update only the card fields sent. Status and tree place have their own endpoints."""
    bare = _task_code(code)
    _live(await _require_task(bare))
    given = payload.model_fields_set
    for field in ("title", "description", "context", "constraints", "criteria", "body", "type", "priority"):
        if field in given and getattr(payload, field) is None:
            raise ApiError.bad_request(f"{field} cannot be null — send an empty string to clear it")
    try:
        row = await task_crud.task_update(
            bare,
            title=payload.title,
            description=payload.description,
            context=payload.context,
            constraints=payload.constraints,
            criteria=payload.criteria,
            body=payload.body,
            type=payload.type,
            priority=payload.priority,
            # For CRUD ``None`` is "leave alone", ``""`` is "clear the group".
            group_code=(
                (_bare(payload.group_code, GROUP_CODE_PREFIX) or "")
                if "group_code" in given
                else None
            ),
            deadline_at=payload.deadline_at if "deadline_at" in given else task_crud.KEEP,
        )
    except ValueError as error:
        raise ApiError.bad_request(str(error)) from error
    if row is None:
        raise ApiError.not_found("Task not found", code=TASK_NOT_FOUND)
    return await _detail(row)


@router.post("/tasks/{code}/status")
async def set_task_status(code: str, payload: TaskStatusBody) -> TaskDetail:
    """Change the status — and with it the phase mark (start, completion, cancellation).

    A separate endpoint, not a field of the general update: only this path stamps the mark, and
    a second way to write ``status`` would mean "done" without a completion date.
    """
    bare = _task_code(code)
    _live(await _require_task(bare))
    try:
        row = await task_crud.task_update_status(bare, payload.status)
    except ValueError as error:
        raise ApiError.bad_request(str(error)) from error
    if row is None:
        raise ApiError.not_found("Task not found", code=TASK_NOT_FOUND)
    return await _detail(row)


@router.post("/tasks/{code}/move")
async def move_task(code: str, payload: TaskMoveBody) -> TaskDetail:
    """Move a task: a new parent (empty — the root) and a position among siblings."""
    bare = _task_code(code)
    _live(await _require_task(bare))
    try:
        link = await link_crud.link_move(
            bare,
            parent_code=_bare(payload.parent_code, TASK_CODE_PREFIX),
            sort=payload.sort,
        )
    except ValueError as error:
        # A cycle in the tree, a foreign workspace, a nonexistent parent — all of it is a wrong
        # argument, not a missing record.
        raise ApiError.bad_request(str(error)) from error
    if link is None:
        raise ApiError.not_found("Task not found", code=TASK_NOT_FOUND)
    return await _detail(await _require_task(bare))


@router.post("/tasks/{code}/reorder")
async def reorder_task(code: str, payload: TaskReorderBody) -> TaskDetail:
    """Drag of a list row: a new place among siblings and, if it was dragged onto another card or
    up out of a branch, a new group and a new parent.

    One mouse gesture — one request: were the group changed by one endpoint, the parent by
    another and the order by a third, the list could manage to show the task in its new group at
    its old place, and the person would see a state they never asked for.

    Parent, group and position are one transaction (``task_crud.task_reorder``): a wrong sibling
    rolls back the move too, so the person never sees an error next to an already moved task.
    """
    bare = _task_code(code)
    _live(await _require_task(bare))
    sent = payload.model_fields_set
    try:
        # An empty string is CRUD's only form of "none": ``None`` there means "leave alone".
        row = await task_crud.task_reorder(
            bare,
            after_code=_bare(payload.after_code, TASK_CODE_PREFIX),
            group_code=(
                _bare(payload.group_code, GROUP_CODE_PREFIX) or ""
                if "group_code" in sent
                else None
            ),
            parent_code=(
                _bare(payload.parent_code, TASK_CODE_PREFIX) or ""
                if "parent_code" in sent
                else None
            ),
        )
    except ValueError as error:
        raise ApiError.bad_request(str(error)) from error
    if row is None:
        raise ApiError.not_found("Task not found", code=TASK_NOT_FOUND)
    return await _detail(await _require_task(bare))


@router.delete("/tasks/{code}", status_code=204)
async def delete_task(code: str) -> Response:
    """Soft delete — together with the whole branch under the task.

    The branch goes as a whole for the same reason it is restored as a whole: a subtask without
    its parent is not work but a fragment. Deleting an already deleted task again is not an
    error — the result matches what was wanted.
    """
    if not await task_crud.task_delete(_task_code(code)):
        raise ApiError.not_found("Task not found", code=TASK_NOT_FOUND)
    return Response(status_code=204)


@router.post("/tasks/{code}/restore")
async def restore_task(code: str) -> TaskDetail:
    """Bring back the task and the descendants that went with it.

    A live one cannot be restored: that is not "already fine" but a sign the button was pressed
    on the wrong row, and a silent "ok" would hide the mismatch between screen and database.
    """
    bare = _task_code(code)
    existing = await _require_task(bare)
    if existing.deleted_at is None:
        raise ApiError.conflict("Task is not deleted — nothing to restore", code=TASK_NOT_DELETED)
    await task_crud.task_restore(bare)
    return await _detail(await _require_task(bare))


@router.delete("/tasks/{code}/purge", status_code=204)
async def purge_task(code: str) -> Response:
    """Hard delete of the task with the whole branch under it — nothing will be left to restore.

    Descendants are enumerated explicitly (CRUD does it): an FK cascade would remove only the
    edges, leaving the child tasks in the database with no place in the tree at all — invisible
    to any traversal.
    """
    if not await task_crud.task_delete(_task_code(code), hard=True):
        raise ApiError.not_found("Task not found", code=TASK_NOT_FOUND)
    return Response(status_code=204)


# ── plan stages ───────────────────────────────────────────────────────────────


class StageBody(_Body):
    """Body for creating and updating a stage.

    ``number`` is optional: when omitted the stage goes next in line. An explicit value is needed
    exactly for inserting in the middle, and then the caller shifts the tail.

    ``evidence`` is included, ``status`` is not: closing a stage checks the evidence, and a
    separate endpoint does that.
    """

    title: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=TITLE_MAX)
    ]
    description: Annotated[
        str, StringConstraints(strip_whitespace=True, max_length=DESCRIPTION_MAX)
    ] = ""
    body: str = ""
    evidence: str = ""
    number: int | None = None


class StageStatusBody(_Body):
    """One status — same as for a task."""

    status: str


def _stage_code(value: str) -> str:
    """Bare stage code from a path segment."""
    return _bare(value, STAGE_CODE_PREFIX) or ""


async def _require_stage(code: str):
    """A stage, or 404."""
    row = await stage_crud.stage_get(code)
    if row is None:
        raise ApiError.not_found("Stage not found", code=STAGE_NOT_FOUND)
    return row


@router.get("/tasks/{code}/stages")
async def list_stages(code: str) -> list[StageRow]:
    """A task's stages by number: the plan reads top to bottom."""
    bare = _task_code(code)
    await _require_task(bare)
    rows = await stage_crud.stage_list_by_task(bare)
    return [StageRow.model_validate(row) for row in rows]


@router.post("/tasks/{code}/stages", status_code=201)
async def create_stage(code: str, payload: StageBody) -> StageRow:
    """Create a stage in a live task."""
    bare = _task_code(code)
    _live(await _require_task(bare))
    try:
        row = await stage_crud.stage_create(
            task_code=bare,
            title=payload.title,
            number=payload.number,
            description=payload.description,
            body=payload.body,
        )
    except ValueError as error:
        raise ApiError.bad_request(str(error)) from error
    return StageRow.model_validate(row)


@router.put("/stages/{code}")
async def update_stage(code: str, payload: StageBody) -> StageRow:
    """Full replacement of a stage card. Status is excluded — see ``POST /stages/{code}/status``."""
    bare = _stage_code(code)
    await _require_stage(bare)
    try:
        row = await stage_crud.stage_update(
            bare,
            title=payload.title,
            description=payload.description,
            body=payload.body,
            number=payload.number,
            evidence=payload.evidence,
        )
    except ValueError as error:
        raise ApiError.bad_request(str(error)) from error
    if row is None:
        raise ApiError.not_found("Stage not found", code=STAGE_NOT_FOUND)
    return StageRow.model_validate(row)


@router.post("/stages/{code}/status")
async def set_stage_status(code: str, payload: StageStatusBody) -> StageRow:
    """Change a stage's status.

    Closing requires evidence: ``done`` with an empty ``evidence`` answers 400 — that gate is
    exactly why the field exists separately from the description.
    """
    bare = _stage_code(code)
    await _require_stage(bare)
    try:
        row = await stage_crud.stage_update_status(bare, payload.status)
    except TaskRuleError as error:
        # The rule code rides in the response next to the text: the UI shows its own wording, and
        # the agent reads the same English phrase as in the logs.
        raise ApiError.bad_request(str(error), code=error.code) from error
    except ValueError as error:
        raise ApiError.bad_request(str(error)) from error
    if row is None:
        raise ApiError.not_found("Stage not found", code=STAGE_NOT_FOUND)
    return StageRow.model_validate(row)


@router.delete("/stages/{code}", status_code=204)
async def delete_stage(code: str) -> Response:
    """Hard delete a stage. It has no soft delete: an abandoned stage is the ``canceled`` status."""
    if not await stage_crud.stage_delete(_stage_code(code)):
        raise ApiError.not_found("Stage not found", code=STAGE_NOT_FOUND)
    return Response(status_code=204)


# ── journal ───────────────────────────────────────────────────────────────────


class NoteBody(_Body):
    """Body for creating a journal entry: kind, subject and, for a fact, the resolution up front.

    ``stage_code`` ties the entry to a stage; without it the entry belongs to the task as a whole.
    """

    type: str
    title: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=TITLE_MAX)
    ]
    body: str = ""
    resolution: str = ""
    stage_code: str | None = None


class NoteResolutionBody(_Body):
    """An entry's resolution — what it is closed with."""

    resolution: str


def _note_code(value: str) -> str:
    """Bare journal entry code from a path segment."""
    return _bare(value, NOTE_CODE_PREFIX) or ""


@router.get("/tasks/{code}/notes")
async def list_notes(
    code: str,
    type: str | None = Query(None, description="Only entries of this kind"),
    open_only: bool = Query(False, description="Only unresolved entries"),
) -> list[NoteRow]:
    """The task's journal in order of appearance."""
    bare = _task_code(code)
    await _require_task(bare)
    rows = await note_crud.note_list_by_task(bare, type=type, open_only=open_only)
    return [NoteRow.model_validate(row) for row in rows]


@router.post("/tasks/{code}/notes", status_code=201)
async def create_note(code: str, payload: NoteBody) -> NoteRow:
    """Append an entry to a live task's journal."""
    bare = _task_code(code)
    _live(await _require_task(bare))
    try:
        row = await note_crud.note_create(
            task_code=bare,
            type=payload.type,
            title=payload.title,
            body=payload.body,
            stage_code=_bare(payload.stage_code, STAGE_CODE_PREFIX),
            resolution=payload.resolution,
        )
    except ValueError as error:
        raise ApiError.bad_request(str(error)) from error
    return NoteRow.model_validate(row)


@router.post("/notes/{code}/resolve")
async def resolve_note(code: str, payload: NoteResolutionBody) -> NoteRow:
    """Close an entry with a resolution.

    Closing it again answers 409: the journal is append-only, and rewriting a resolution after the
    fact would bend history to fit the outcome. Changed your mind — write a new entry.
    """
    bare = _note_code(code)
    try:
        row = await note_crud.note_resolve(bare, payload.resolution)
    except TaskRuleError as error:
        # 409, not 400: the entry exists and is valid — it is the state that does not fit, as when
        # editing a deleted row.
        raise ApiError.conflict(str(error), code=error.code) from error
    except ValueError as error:
        raise ApiError.bad_request(str(error)) from error
    if row is None:
        raise ApiError.not_found("Journal entry not found", code=NOTE_NOT_FOUND)
    return NoteRow.model_validate(row)


@router.delete("/notes/{code}", status_code=204)
async def delete_note(code: str) -> Response:
    """Hard delete an entry — a person's endpoint, never exposed to the agent."""
    if not await note_crud.note_delete(_note_code(code)):
        raise ApiError.not_found("Journal entry not found", code=NOTE_NOT_FOUND)
    return Response(status_code=204)


__all__ = [
    "GroupBody",
    "NoteBody",
    "NoteResolutionBody",
    "StageBody",
    "StageStatusBody",
    "TaskCreateBody",
    "TaskMoveBody",
    "TaskStatusBody",
    "TaskUpdateBody",
    "router",
]
