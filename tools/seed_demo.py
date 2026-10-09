"""Demo data seeder for the ``tasks`` module: workspaces, groups, tasks, stages and the journal.

Meant for debugging the interface: an empty list tests nothing, and typing in thirty-odd tasks with
stages and a journal by hand costs half an hour per run. The script lays down a coherent slice in
which every enum value and every state the interface must be able to show occurs at least once.

**Writes to the database from ``.env``** — the same one the application sees (``Config()`` reads
the provider and path from there). It writes ONLY by inserting: there is no ``DROP``, ``TRUNCATE``
or ``DELETE`` here and there must never be — a demo workspace can be removed from the interface,
while bulk deletes from a script are irreversible.

Data goes in through the module's CRUD, not through raw ``INSERT``: it is the same path the
application takes, so a row the backend would reject cannot appear here either. A side benefit is
that phase timestamps (``started_at`` and friends) are set by the status change itself, not by hand.

Every run adds a NEW set: codes are random, and a second run yields a second set of workspaces with
the same contents. That is intended — comparing two slices is easier than guessing what changed in one.

    uv run python tools/seed_demo.py           # three workspaces with the full set
    uv run python tools/seed_demo.py --small   # one workspace, no branches and no trash
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.core.config import Config
from src.core.database import close_database, init_database
from src.core.utils.date import utc_now
from src.modules.tasks.constants import (
    ACTOR_AGENT,
    JOURNAL_DECISION,
    JOURNAL_FACT,
    JOURNAL_FINDING,
    JOURNAL_REMARK,
    PRIORITY_BURNING,
    PRIORITY_FROZEN,
    PRIORITY_HIGH,
    PRIORITY_LOW,
    PRIORITY_NORMAL,
    STATUS_BACKLOG,
    STATUS_CANCELED,
    STATUS_DONE,
    STATUS_IN_PROGRESS,
    STATUS_IN_REVIEW,
    STATUS_IN_TEST,
    STATUS_PLANNED,
    TYPE_EXTENDED,
    TYPE_SIMPLE,
    TYPE_STANDARD,
)
from src.modules.tasks.crud import group as group_crud
from src.modules.tasks.crud import link as link_crud
from src.modules.tasks.crud import journal as journal_crud
from src.modules.tasks.crud import stage as stage_crud
from src.modules.tasks.crud import task as task_crud
from src.modules.workspace.crud import workspace as workspace_crud

MARK = "demo data"
"""Marker in the workspace description: it lets a person tell seeded data from their own."""


# ── what gets seeded ──────────────────────────────────────────────────────────
# The contents are described as data, not code: adding a task is a line in a list, not a branch in a function.

WORKSPACES = [
    {
        "title": "Demo: development",
        "description": f"A product team's workspace ({MARK})",
        "color": "indigo",
        "icon": "code",
        "groups": [
            {"title": "Billing", "description": "Plans, invoices, payments", "color": "amber", "icon": "wallet"},
            {"title": "Interface", "description": "Screens, forms, layout", "color": "sky", "icon": "layout"},
            {"title": "Infrastructure", "description": "Build, deploy, monitoring", "color": "slate", "icon": "server"},
            # A group with no tasks ON PURPOSE: the list shows such groups dimmed at the bottom, and
            # they also serve as drop targets. Without an empty group in the data this case is never seen.
            {"title": "Documentation", "description": "Texts, README, help", "color": "teal", "icon": "notebook"},
        ],
    },
    {
        "title": "Demo: personal",
        "description": f"Things outside work ({MARK})",
        "color": "green",
        "icon": "home",
        "groups": [
            {"title": "Health", "description": "Doctors, sport, routine", "color": "rose", "icon": "heart"},
            {"title": "Home", "description": "Chores and repairs", "color": "orange", "icon": "tool"},
        ],
    },
    {
        "title": "Demo: client",
        "description": f"An external project with acceptance ({MARK})",
        "color": "violet",
        "icon": "briefcase",
        "groups": [
            {"title": "Integration", "description": "Data exchange with their system", "color": "cyan", "icon": "plug"},
        ],
    },
]

# Tasks of the first workspace are the densest slice: all three types, every status, a branch with
# subtasks, a deleted row and a task without a group.
DEV_TASKS = [
    {
        "title": "Move pricing plans to the new schema",
        "description": "Plans are priced from the new table; the old column is read nowhere",
        "group": "Billing",
        "type": TYPE_EXTENDED,
        "status": STATUS_IN_PROGRESS,
        "priority": PRIORITY_BURNING,
        "deadline_days": 3,
        "context": (
            "The schema is described in `docs/billing/pricing.md`. The old `plan_code` field is read "
            "by three modules; the list is in the TASK@ below.\n\n"
            "The reference for the move is migration `bil_004`, which also shows the dual-write technique."
        ),
        "constraints": (
            "- allowed: change the billing code and its migrations\n"
            "- ask first: any change to the public API\n"
            "- never: touch the `workspace` module or other modules' tables"
        ),
        "criteria": (
            "1. `pytest tests/modules/billing -q` is green\n"
            "2. The old column is not read: grep for `plan_code` is empty\n"
            "3. The migration rolls back and forward on a copy of the production database"
        ),
        "plan": (
            "Going through the layers bottom up: migration → models → CRUD → API → frontend.\n\n"
            "Read: `models/pricing.py`, `crud/pricing.py`, `api.py`, migrations `bil_001…004`.\n"
            "Will change: the same files plus `web/src/features/billing/api.ts`."
        ),
        "progress": (
            "- Migration `bil_005` written, rolls back and forward → CRUD next.\n"
            "- CRUD reads the new table; the list response breaks on the old field → investigating."
        ),
        "stages": [
            {"title": "Migration and models", "description": "New table and value transfer", "status": STATUS_DONE,
             "evidence": "tsm-style migration bil_005; pytest tests/modules/billing/test_migrations.py → 4 passed"},
            {"title": "CRUD and API", "description": "Reads go through the new table", "status": STATUS_IN_PROGRESS,
             "body": "Serialising the old field in the list response breaks — investigating."},
            {"title": "Frontend and column removal", "description": "Client update and legacy removal", "status": STATUS_PLANNED},
        ],
        "journal": [
            {"type": JOURNAL_DECISION, "title": "Dual write for the duration of the move",
             "body": "Write to both tables, read from the new one. Otherwise a rollback loses a day of payments.",
             "resolution": "Checked on a database copy: no discrepancies"},
            {"type": JOURNAL_DECISION, "title": "What to do with invoices from before 2024",
             "body": "Move them, or keep them in an archive table? No answer yet — not moving them for now."},
            {"type": JOURNAL_FACT, "title": "Rows in pricing_plan: 1842", "body": "61 of them live",
             "resolution": "recorded"},
            {"type": JOURNAL_FINDING, "title": "N+1 on the invoice list in `crud/invoice.py`",
             "body": "Every row fetches its plan with a separate query. Not part of this task."},
        ],
        "children": [
            {"title": "Update the billing client", "type": TYPE_STANDARD, "status": STATUS_PLANNED,
             "priority": PRIORITY_HIGH, "description": "The frontend reads the new field"},
            {"title": "Drop the legacy column", "type": TYPE_SIMPLE, "status": STATUS_BACKLOG,
             "priority": PRIORITY_LOW, "description": "Once everything has moved"},
        ],
    },
    {
        "title": "Invoice form does not save the comment",
        "description": "The comment reaches the backend and is saved",
        "group": "Billing",
        # Only an extended task has stages — on a standard one the CRUD would refuse this same set.
        "type": TYPE_EXTENDED,
        "status": STATUS_IN_REVIEW,
        "priority": PRIORITY_HIGH,
        "deadline_days": 1,
        "context": "Reproduces on the invoice form: the field is filled in, and empty after saving.",
        "criteria": "1. The comment is visible after a page reload\n2. A regression test",
        "plan": "Looks like a full card replacement without the field: the form does not send `comment`.",
        "result": (
            "Both invoice forms send `comment` in the PUT body; the field survives a reload. "
            "Pinned by `test_api_invoice.py::test_update_keeps_comment`."
        ),
        "stages": [
            {"title": "Reproduce", "description": "Find where it gets lost", "status": STATUS_DONE,
             "evidence": "DevTools: the PUT body has no comment key"},
            {"title": "Fix and pin with a test", "status": STATUS_DONE,
             "evidence": "pytest tests/modules/billing/test_api_invoice.py -q → 12 passed"},
        ],
        "journal": [
            {"type": JOURNAL_REMARK, "title": "Check the edit form too, not only the create form",
             "body": "From the task's author, during the work.", "resolution": "Checked — same bug there, fixed both"},
        ],
    },
    {
        "title": "Dark theme: cards lose their border",
        "description": "The card border is visible in both themes",
        "group": "Interface",
        "type": TYPE_EXTENDED,
        "status": STATUS_IN_TEST,
        "priority": PRIORITY_NORMAL,
        "context": "In the dark theme the `--border` token equals the background.",
        "constraints": "- never: change the whole palette — only the border token is fixed",
        "criteria": "1. A screenshot of both themes\n2. Contrast no lower than 1.5:1",
        "plan": "Changing the token and going through every place that uses it.",
        "stages": [
            {"title": "Token fix", "status": STATUS_DONE, "evidence": "web/src/styles/tokens.css:41"},
            {"title": "Screen walkthrough", "description": "Tasks, groups, workspaces, research", "status": STATUS_IN_PROGRESS},
        ],
        "journal": [
            {"type": JOURNAL_FACT, "title": "Contrast was 1.02:1", "body": "Measured in DevTools", "resolution": "recorded"},
        ],
    },
    {
        "title": "Task list: sections by group",
        "description": "Tasks are laid out by group, with \"No group\" last",
        "group": "Interface",
        "type": TYPE_STANDARD,
        "status": STATUS_DONE,
        "priority": PRIORITY_NORMAL,
        "context": "The store computes the layout; the page only renders it.",
        "criteria": "1. Empty groups sit at the bottom, dimmed\n2. \"No group\" comes last",
        # No stages here on purpose: this is the sample STANDARD task, whose plan lives in prose.
        # Without such an example the demo would show only extended tasks, and the difference
        # between the levels would remain words in the handbook.
        "plan": "Grouping in a computed, the backend sets the order. Touched stores/tasks.store.ts "
                "(sections) and components/TaskListTable.vue.",
        "journal": [
            {"type": JOURNAL_DECISION, "title": "The \"No group\" section goes last",
             "body": "It is the remainder, not a theme on par with the others.", "resolution": "Agreed with the task's author"},
        ],
    },
    {
        "title": "Upgrade Python to 3.13",
        "description": "Build and tests run on 3.13",
        "group": "Infrastructure",
        "type": TYPE_EXTENDED,
        "status": STATUS_BACKLOG,
        "priority": PRIORITY_LOW,
        "context": "Dependencies are half-checked: `greenlet` and `asyncpg` are in question.",
        "constraints": "- ask first: dependency upgrades with breaking changes",
        "criteria": "1. The full test run is green on 3.13\n2. The frontend build is unaffected",
        "plan": "A run on a branch first, then an update of the installation's environment.",
        "journal": [
            {"type": JOURNAL_DECISION, "title": "Waiting for an asyncpg release that supports 3.13",
             "body": "Otherwise it has to be built from source."},
        ],
    },
    {
        "title": "Frozen: move production to Postgres",
        "description": "Production runs on Postgres",
        "group": "Infrastructure",
        "type": TYPE_STANDARD,
        "status": STATUS_PLANNED,
        "priority": PRIORITY_FROZEN,
        "context": "The decision is postponed until the end of the quarter.",
        "plan": "There is a plan, no dates.",
    },
    {
        "title": "Sort through incoming ideas",
        "description": "The idea list is sorted, the rest closed",
        "group": None,
        "type": TYPE_SIMPLE,
        "status": STATUS_BACKLOG,
        "priority": PRIORITY_NORMAL,
        "context": "A task outside any group — exercises the \"No group\" section.",
    },
    {
        "title": "Canceled plugin idea",
        "description": "Third-party plugins",
        "group": "Infrastructure",
        "type": TYPE_STANDARD,
        "status": STATUS_CANCELED,
        "priority": PRIORITY_LOW,
        "context": "Closed: a single-developer tool has nobody to write plugins.",
    },
    {
        "title": "Deleted task from last sprint",
        "description": "Sits in the trash — exercises the \"show deleted\" toggle",
        "group": "Billing",
        "type": TYPE_SIMPLE,
        "status": STATUS_BACKLOG,
        "priority": PRIORITY_NORMAL,
        "deleted": True,
    },
]

PERSONAL_TASKS = [
    {
        "title": "Book a dentist appointment",
        "description": "The appointment is booked",
        "group": "Health",
        "type": TYPE_SIMPLE,
        "status": STATUS_PLANNED,
        "priority": PRIORITY_HIGH,
        "deadline_days": 5,
    },
    {
        "title": "Clear out the storeroom",
        "description": "The storeroom is sorted, the junk taken out",
        "group": "Home",
        "type": TYPE_SIMPLE,
        "status": STATUS_BACKLOG,
        "priority": PRIORITY_LOW,
    },
    {
        "title": "Assemble the study shelf",
        "description": "The shelf stands and holds books",
        "group": "Home",
        "type": TYPE_SIMPLE,
        "status": STATUS_DONE,
        "priority": PRIORITY_NORMAL,
        "deadline_days": -2,
    },
]

CLIENT_TASKS = [
    {
        "title": "Order exchange through their API",
        "description": "Orders arrive and are confirmed automatically",
        "group": "Integration",
        "type": TYPE_EXTENDED,
        "status": STATUS_IN_PROGRESS,
        "priority": PRIORITY_HIGH,
        "deadline_days": 10,
        "context": (
            "Their API documentation is in the contract appendix, version 2.3.\n"
            "The test environment is slow: up to 8 seconds per request."
        ),
        "constraints": (
            "- allowed: create our own tables for the exchange queue\n"
            "- ask first: any change to the contractual format\n"
            "- never: write to their production environment from our machine"
        ),
        "criteria": (
            "1. An order from their test environment arrives and is confirmed\n"
            "2. Redelivering the same order does not create a duplicate\n"
            "3. A refusal from their side shows in the task journal, not only in the logs"
        ),
        "plan": "A queue on our side, retries with exponential backoff, idempotency by their id.",
        "stages": [
            {"title": "Their API client", "status": STATUS_DONE, "evidence": "src/modules/exchange/client.py; 9 tests green"},
            {"title": "Queue and retries", "status": STATUS_IN_PROGRESS, "body": "Retries are done, idempotency in progress."},
            {"title": "Acceptance on their environment", "status": STATUS_PLANNED, "description": "A joint run with their engineer"},
            {"title": "Abandoned webhook approach", "status": STATUS_CANCELED,
             "description": "Their side does not send webhooks — dropped"},
        ],
        "journal": [
            {"type": JOURNAL_REMARK, "title": "The deadline cannot move, acceptance is on the 30th",
             "body": "From the client on a call."},
            {"type": JOURNAL_DECISION, "title": "Idempotency by their order_id, not ours",
             "body": "Their id is stable across retries; ours is generated on insert.",
             "resolution": "Checked: a retry does not create a duplicate"},
            {"type": JOURNAL_FINDING, "title": "Their test environment returns 500 on an empty list",
             "body": "Not our area, but their team should be told."},
            {"type": JOURNAL_FACT, "title": "Their API timeout is 8 s per request",
             "body": "Measured over 50 requests, median 3.1 s", "resolution": "recorded"},
        ],
    },
    {
        "title": "Integration report for the client",
        "description": "The report is sent and accepted",
        "group": "Integration",
        "type": TYPE_STANDARD,
        "status": STATUS_IN_REVIEW,
        "priority": PRIORITY_NORMAL,
        "deadline_days": 2,
        "criteria": "1. The report covers all three stages\n2. Run numbers are attached",
        "plan": "Assembling it from the journal of the task above.",
    },
]


# ── assembly ──────────────────────────────────────────────────────────────────


# Every key a task spec may carry. A key outside it is a typo or a renamed field — ``body`` once
# quietly seeded empty plans — and fails the seeding instead of vanishing.
TASK_SPEC_KEYS = frozenset({
    "title", "description", "context", "constraints", "criteria", "plan", "progress", "result",
    "type", "status", "priority", "group", "created_by", "deadline_days", "deleted",
    "stages", "journal", "children",
})


async def seed_task(*, workspace_code: str, spec: dict, groups: dict[str, str], parent_code: str | None = None) -> str:
    """Create a task with all of its contents and return its code."""
    unknown = set(spec) - TASK_SPEC_KEYS
    if unknown:
        raise ValueError(f"Task spec {spec['title']!r} carries unknown keys: {sorted(unknown)}")
    deadline = None
    if spec.get("deadline_days") is not None:
        deadline = utc_now() + timedelta(days=spec["deadline_days"])

    task = await task_crud.task_create(
        workspace_code=workspace_code,
        title=spec["title"],
        description=spec.get("description", ""),
        context=spec.get("context", ""),
        constraints=spec.get("constraints", ""),
        criteria=spec.get("criteria", ""),
        plan=spec.get("plan", ""),
        progress=spec.get("progress", ""),
        result=spec.get("result", ""),
        type=spec.get("type", TYPE_SIMPLE),
        priority=spec.get("priority", PRIORITY_NORMAL),
        group_code=groups.get(spec["group"]) if spec.get("group") else None,
        parent_code=parent_code,
        created_by=spec.get("created_by", ACTOR_AGENT if spec.get("type") != TYPE_SIMPLE else "human"),
        deadline_at=deadline,
    )

    # The status is set separately: only this path stamps the phase timestamps, and demo data must
    # look like real data — with a start date on everything already in progress.
    status = spec.get("status", STATUS_BACKLOG)
    if status != STATUS_BACKLOG:
        await task_crud.task_update_status(task.code, status)

    for stage_spec in spec.get("stages", []):
        stage = await stage_crud.stage_create(
            task_code=task.code,
            title=stage_spec["title"],
            description=stage_spec.get("description", ""),
            body=stage_spec.get("body", ""),
        )
        if stage_spec.get("evidence"):
            await stage_crud.stage_update(stage.code, evidence=stage_spec["evidence"])
        stage_status = stage_spec.get("status", STATUS_PLANNED)
        if stage_status != STATUS_PLANNED:
            # A closed stage passes through in-progress: otherwise it would have no start timestamp.
            if stage_status in (STATUS_DONE, STATUS_IN_REVIEW, STATUS_IN_TEST):
                await stage_crud.stage_update_status(stage.code, STATUS_IN_PROGRESS)
            await stage_crud.stage_update_status(stage.code, stage_status)

    for entry_spec in spec.get("journal", []):
        await journal_crud.journal_create(
            task_code=task.code,
            type=entry_spec["type"],
            title=entry_spec["title"],
            body=entry_spec.get("body", ""),
            resolution=entry_spec.get("resolution", "") if entry_spec["type"] == JOURNAL_FACT else "",
        )
        if entry_spec.get("resolution") and entry_spec["type"] != JOURNAL_FACT:
            entries = await journal_crud.journal_list_by_task(task.code)
            await journal_crud.journal_resolve(entries[-1].code, entry_spec["resolution"])

    for child in spec.get("children", []):
        await seed_task(workspace_code=workspace_code, spec=child, groups=groups, parent_code=task.code)

    if spec.get("deleted"):
        await task_crud.task_delete(task.code)

    return task.code


async def seed_workspace(spec: dict, tasks: list[dict]) -> dict:
    """A whole workspace: card, groups, tasks. Returns counters for the report."""
    workspace = await workspace_crud.workspace_create(
        title=spec["title"],
        description=spec["description"],
        color=spec["color"],
        icon=spec["icon"],
    )
    groups: dict[str, str] = {}
    for index, group_spec in enumerate(spec["groups"]):
        group = await group_crud.group_create(
            workspace_code=workspace.code,
            title=group_spec["title"],
            description=group_spec["description"],
            color=group_spec["color"],
            icon=group_spec["icon"],
            # The first group goes on top: a larger `sort` comes first, and equal values would give
            # alphabetical order instead of the intended layout.
            sort=500 + (len(spec["groups"]) - index) * 10,
        )
        groups[group_spec["title"]] = group.code

    for task_spec in tasks:
        await seed_task(workspace_code=workspace.code, spec=task_spec, groups=groups)

    rows = await task_crud.task_list_by_workspace(workspace.code, include_deleted=True)
    return {"workspace": workspace.title, "code": workspace.code, "groups": len(groups), "tasks": len(rows)}


async def main(small: bool) -> int:
    config = Config()
    target = config.db_path or config.db_name or "default"
    print(f"database: {config.db_provider} → {target}")

    plan = [(WORKSPACES[0], DEV_TASKS)]
    if not small:
        plan += [(WORKSPACES[1], PERSONAL_TASKS), (WORKSPACES[2], CLIENT_TASKS)]

    await init_database(config)
    try:
        report = [await seed_workspace(spec, tasks) for spec, tasks in plan]
    finally:
        await close_database()

    print("\nseeded:")
    for row in report:
        print(f"  {row['workspace']} ({row['code']}): groups {row['groups']}, tasks {row['tasks']}")
    print('\nremove the demo from the interface: "Workspaces" → delete → "Delete forever".')
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Demo data for the tasks module: workspaces, groups, tasks.")
    parser.add_argument("--small", action="store_true", help="only the single development workspace")
    args = parser.parse_args()
    raise SystemExit(asyncio.run(main(args.small)))
