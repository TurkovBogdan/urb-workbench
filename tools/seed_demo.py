"""Demo data seeder: workspaces, groups, tasks with stages, journal and notes, codexes with their
trees and mounts.

Meant for debugging the interface: an empty list tests nothing, and typing in thirty-odd tasks with
stages and a journal by hand costs half an hour per run. The script lays down a coherent slice in
which every enum value and every state the interface must be able to show occurs at least once —
including the trash (a deleted workspace, task, codex and codex note), an empty workspace, a codex
switched off in a workspace and a codex tree at its depth limit.

**Writes to the database from ``.env``** — the same one the application sees (``Config()`` reads
the provider and path from there). It writes ONLY by inserting: there is no ``DROP``, ``TRUNCATE``
or ``DELETE`` here and there must never be — a demo workspace can be removed from the interface,
while bulk deletes from a script are irreversible.

Data goes in through the module's CRUD, not through raw ``INSERT``: it is the same path the
application takes, so a row the backend would reject cannot appear here either. A side benefit is
that phase timestamps (``started_at`` and friends) are set by the status change itself, not by hand.

Every run adds a NEW set: codes are random, and a second run yields a second set of workspaces with
the same contents. That is intended — comparing two slices is easier than guessing what changed in one.
Codex segments are unique across the installation, so a second run's codexes come as ``python-2`` and so on.

    uv run python tools/seed_demo.py           # every codex and eight workspaces, the bulk included
    uv run python tools/seed_demo.py --small   # the hand-written codexes and only "Demo: development"
    uv run python tools/seed_demo.py --bulk    # only the long texts and the volume (``seed_demo_bulk.py``)
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import textwrap
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.core.config import Config
from src.core.database import close_database, init_database
from src.core.utils.date import utc_now
from src.modules.codex.crud import codex as codex_crud
from src.modules.codex.crud import mount as mount_crud
from src.modules.codex.crud import note as codex_note_crud
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
from src.modules.tasks.crud import note as task_note_crud
from src.modules.tasks.crud import stage as stage_crud
from src.modules.tasks.crud import task as task_crud
from src.modules.workspace.crud import workspace as workspace_crud

# A sibling script, found because Python puts the running script's folder on the path.
import seed_demo_bulk as bulk

MARK = "demo data"
"""Marker in the workspace description: it lets a person tell seeded data from their own."""


def md(text: str) -> str:
    """A markdown body written indented inside the specs below, as the document it stands for."""
    return textwrap.dedent(text).strip()


# ── what gets seeded ──────────────────────────────────────────────────────────
# The contents are described as data, not code: adding a task is a line in a list, not a branch in a function.

# Colors and icons are names from the frontend palettes (`web/src/shared/colors.ts`, `icons.ts`): a
# name outside them is stored without complaint and renders as nothing.
#
# ``codexes`` mounts codexes by their spec segment, in that order; ``off`` mounts and switches off again,
# so the row keeps its place and shows as disabled. ``deleted`` sends the workspace to the trash.
WORKSPACES = [
    {
        "title": "Demo: development",
        "description": f"A product team's workspace ({MARK})",
        "color": "blue",
        "icon": "code",
        "groups": [
            {"title": "Billing", "description": "Plans, invoices, payments", "color": "yellow", "icon": "coins"},
            {"title": "Interface", "description": "Screens, forms, layout", "color": "sky", "icon": "palette"},
            {"title": "Infrastructure", "description": "Build, deploy, monitoring", "color": "slate", "icon": "server"},
            # A group with no tasks ON PURPOSE: the list shows such groups dimmed at the bottom, and
            # they also serve as drop targets. Without an empty group in the data this case is never seen.
            {"title": "Documentation", "description": "Texts, README, help", "color": "teal", "icon": "notebook"},
        ],
        "codexes": [
            {"segment": "python", "agent_can_edit": True},
            {"segment": "vue", "agent_can_edit": True},
            {"segment": "sql", "agent_can_edit": False},
            {"segment": "git", "agent_can_edit": False},
            {"segment": "writing", "agent_can_edit": True},
            {"segment": "security", "off": True},
        ],
    },
    {
        "title": "Demo: personal",
        "description": f"Things outside work ({MARK})",
        "color": "green",
        "icon": "home",
        "groups": [
            {"title": "Health", "description": "Doctors, sport, routine", "color": "rose", "icon": "heart"},
            {"title": "Home", "description": "Chores and repairs", "color": "orange", "icon": "hammer"},
        ],
        "codexes": [
            {"segment": "writing", "agent_can_edit": False},
        ],
    },
    {
        "title": "Demo: client",
        "description": f"An external project with acceptance ({MARK})",
        "color": "violet",
        "icon": "briefcase",
        "groups": [
            {"title": "Integration", "description": "Data exchange with their system", "color": "teal", "icon": "network"},
        ],
        "codexes": [
            {"segment": "security", "agent_can_edit": False},
            {"segment": "python", "agent_can_edit": False},
            {"segment": "git", "agent_can_edit": False},
        ],
    },
    {
        "title": "Demo: open source",
        "description": f"A public library with releases and outside issues ({MARK})",
        "color": "orange",
        "icon": "package",
        "groups": [
            {"title": "Releases", "description": "Versions, changelog, publishing", "color": "green", "icon": "rocket"},
            {"title": "Issues", "description": "Reports from users", "color": "red", "icon": "bug"},
            {"title": "Community", "description": "Contributors, reviews, docs", "color": "sky", "icon": "users-group"},
        ],
        "codexes": [
            {"segment": "git", "agent_can_edit": True},
            {"segment": "python", "agent_can_edit": True},
            {"segment": "writing", "agent_can_edit": True},
        ],
    },
    # No groups, no tasks, no codexes: the empty states of every page that opens a workspace.
    {
        "title": "Demo: empty",
        "description": f"Nothing inside — exercises the empty states ({MARK})",
        "color": "slate",
        "icon": "box",
        "groups": [],
    },
    {
        "title": "Demo: archived",
        "description": f"Sits in the trash — exercises the deleted workspaces ({MARK})",
        "color": "rose",
        "icon": "archive",
        "groups": [
            {"title": "Old backlog", "description": "What was left when the project closed", "color": "slate", "icon": "folder"},
        ],
        "codexes": [
            {"segment": "python", "agent_can_edit": False},
        ],
        "deleted": True,
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
        "notes": [
            {
                "title": "Схема новой таблицы тарифов",
                "description": "Колонки pricing_plan_v2 и откуда берётся каждое значение",
                "body": md("""
                    ## pricing_plan_v2

                    | Колонка | Тип | Откуда |
                    | --- | --- | --- |
                    | `code` | `VARCHAR(10)` | новый код, генерируется |
                    | `legacy_code` | `VARCHAR(32)` | старый `plan_code`, только на время переезда |
                    | `amount_minor` | `BIGINT` | `price * 100`, копейки вместо `NUMERIC` |
                    | `currency` | `CHAR(3)` | `RUB` для всех старых строк |
                    | `period` | `VARCHAR(16)` | `month` / `year` |
                    | `archived_at` | `TIMESTAMP` | `NULL` у 61 живого тарифа |

                    ### Почему копейки

                    Сумма в `NUMERIC` на SQLite хранится как `REAL`: `19.99 * 3` даёт
                    `59.970000000000006`. Целое число копеек сравнивается без сюрпризов на обоих
                    провайдерах.

                    ### Двойная запись

                    ```python
                    async def plan_update(code: str, **values) -> Plan:
                        async with write_scope() as s:
                            row = await _update_v2(s, code, values)
                            await _mirror_legacy(s, row)  # снимается в «Drop the legacy column»
                        return row
                    ```
                """),
            },
            {
                "title": "Кто читает plan_code",
                "description": "Список мест, которые надо перевести до удаления колонки",
                "body": md("""
                    - [x] `src/modules/billing/crud/invoice.py` — переведено
                    - [x] `src/modules/billing/api.py` — переведено
                    - [ ] `src/modules/reports/monthly.py` — читает напрямую SQL-ом
                    - [ ] `web/src/features/billing/api.ts` — поле в типе `InvoiceRow`
                    - [ ] выгрузка в бухгалтерию (cron, `tools/export_1c.py`)

                    > Выгрузку не трогаем до конца месяца: бухгалтерия сверяет по старому коду.
                """),
            },
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
        "notes": [
            {
                "title": "Шаги воспроизведения",
                "description": "Как поймать баг руками за минуту",
                "body": md("""
                    1. Открыть любой счёт в статусе «черновик».
                    2. Вписать комментарий `проверка 42`, нажать «Сохранить».
                    3. Перезагрузить страницу — поле пустое.

                    Тело запроса из DevTools:

                    ```json
                    {"amount_minor": 159900, "currency": "RUB", "due_at": "2026-10-20"}
                    ```

                    Ключа `comment` нет — форма собирает тело из списка полей, где его забыли.
                """),
            },
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
        "notes": [
            {
                "title": "Их API: эндпоинты, которые мы зовём",
                "description": "Выжимка из приложения к договору, версия 2.3",
                "body": md("""
                    | Метод | Путь | Что | Идемпотентен |
                    | --- | --- | --- | --- |
                    | `GET` | `/v2/orders?since=` | новые заказы с курсора | да |
                    | `POST` | `/v2/orders/{id}/ack` | подтверждение приёма | да, по `order_id` |
                    | `POST` | `/v2/orders/{id}/reject` | отказ с причиной | нет |

                    Авторизация — заголовок `X-Partner-Key`, ключ живёт в `.env` как
                    `EXCHANGE_PARTNER_KEY` и никогда не попадает в лог.

                    ### Коды ответов

                    - `409` на `ack` — заказ уже подтверждён, это успех, а не ошибка;
                    - `500` на пустом списке — их баг, обходим проверкой `Content-Length: 0`;
                    - `429` — ждать `Retry-After`, не меньше 2 секунд.
                """),
            },
            {
                "title": "Протокол созвона 02.10",
                "description": "Что договорились с их инженером",
                "body": md("""
                    **Участники:** мы, их тимлид интеграций, менеджер проекта.

                    - Приёмка 30-го, переноса не будет.
                    - Вебхуков не будет и в следующей версии — только опрос.
                    - Тестовый стенд перезапускают по ночам с 02:00 до 03:00 МСК: ретраи в это
                      окно не считаются инцидентом.
                    - Отказ (`reject`) обязательно с текстовой причиной — их операторы читают её
                      глазами.

                    Следующий созвон — после прогона на их стенде.
                """),
            },
            {
                "title": "Черновик",
                "description": "",
                "body": "",
            },
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

OSS_TASKS = [
    {
        "title": "Release 2.0: drop Python 3.9",
        "description": "2.0 is on PyPI, 3.9 is out of the matrix, the changelog explains why",
        "group": "Releases",
        "type": TYPE_EXTENDED,
        "status": STATUS_IN_PROGRESS,
        "priority": PRIORITY_HIGH,
        "deadline_days": 14,
        "context": (
            "3.9 reached end of life; keeping it blocks `match` and the new typing syntax.\n"
            "Downloads on 3.9 are 4% according to pypistats."
        ),
        "constraints": (
            "- allowed: break the public API where the changelog names it\n"
            "- ask first: renaming anything imported from the package root\n"
            "- never: publish to PyPI from a local machine — only the release workflow"
        ),
        "criteria": (
            "1. CI matrix is 3.10–3.13 and green\n"
            "2. `pip install lib==2.0` works on a clean 3.10\n"
            "3. CHANGELOG has a «Breaking» section with a migration snippet"
        ),
        "plan": "Matrix first, then syntax upgrades module by module, then the deprecation sweep, release last.",
        "progress": "- Matrix moved, green.\n- pyupgrade --py310-plus applied to `core/`, `io/` left.",
        "stages": [
            {"title": "CI matrix", "status": STATUS_DONE, "evidence": "Actions run #812 — 4 jobs green"},
            {"title": "Syntax upgrade", "status": STATUS_IN_PROGRESS, "body": "`core/` done, `io/` in progress."},
            {"title": "Deprecation sweep", "status": STATUS_PLANNED,
             "description": "Remove everything deprecated since 1.4"},
            {"title": "Release", "status": STATUS_PLANNED, "description": "Tag, workflow, announcement"},
        ],
        "journal": [
            {"type": JOURNAL_DECISION, "title": "No 1.x maintenance branch",
             "body": "One maintainer cannot carry two lines; 1.9 gets security fixes for 6 months from master.",
             "resolution": "Announced in discussions, no objections in a week"},
            {"type": JOURNAL_FACT, "title": "3.9 share of downloads: 4.1%", "body": "pypistats, last 30 days",
             "resolution": "recorded"},
        ],
        "notes": [
            {
                "title": "Черновик CHANGELOG 2.0",
                "description": "Раздел Breaking — его читают первым",
                "body": md("""
                    ## 2.0.0 — unreleased

                    ### Breaking

                    - Python 3.9 больше не поддерживается.
                    - `lib.load(path, encoding=None)` → `lib.load(path, *, encoding="utf-8")`:
                      кодировка теперь только именованным аргументом.
                    - Удалён `lib.compat`, объявленный устаревшим в 1.4.

                    ```python
                    # было
                    data = lib.load("a.csv", "cp1251")
                    # стало
                    data = lib.load("a.csv", encoding="cp1251")
                    ```

                    ### Added

                    - `lib.stream()` — построчное чтение без загрузки файла целиком.
                """),
            },
        ],
        "children": [
            {"title": "Announce the release in discussions", "type": TYPE_SIMPLE, "status": STATUS_PLANNED,
             "priority": PRIORITY_NORMAL, "description": "A post with the migration snippet"},
        ],
    },
    {
        "title": "Crash on an empty CSV with a BOM",
        "description": "An empty file with a BOM loads as an empty table",
        "group": "Issues",
        "type": TYPE_STANDARD,
        "status": STATUS_IN_TEST,
        "priority": PRIORITY_BURNING,
        "context": "Issue #431: `IndexError` in `sniff_header` on a three-byte file.",
        "criteria": "1. A regression test with a BOM-only file\n2. Fixed in 1.9.3 and in master",
        "plan": "Strip the BOM before sniffing; an empty remainder returns an empty table early.",
        "result": "Fixed in `io/csv.py:88`; test `test_bom_only_file`. Backported to 1.9.3.",
        "notes": [
            {
                "title": "Минимальный пример из issue",
                "description": "Файл из трёх байт — весь репро",
                "body": md("""
                    ```bash
                    printf '\\xef\\xbb\\xbf' > empty.csv
                    python -c "import lib; print(lib.load('empty.csv'))"
                    ```

                    ```text
                    IndexError: list index out of range
                      File "lib/io/csv.py", line 91, in sniff_header
                    ```
                """),
            },
        ],
    },
    {
        "title": "Typo in the README install section",
        "description": "The command copies and runs",
        "group": "Issues",
        "type": TYPE_SIMPLE,
        "status": STATUS_DONE,
        "priority": PRIORITY_LOW,
        "created_by": "human",
    },
    {
        "title": "Review: async reader from an outside contributor",
        "description": "PR #455 is merged or closed with a reason",
        "group": "Community",
        "type": TYPE_STANDARD,
        "status": STATUS_IN_REVIEW,
        "priority": PRIORITY_NORMAL,
        "deadline_days": 4,
        "context": "The PR adds `lib.aload`; 600 lines, no tests for cancellation.",
        "criteria": "1. Cancellation is tested\n2. The sync path is not slower (bench in the PR)",
        "plan": "Review in two passes: API shape first, then the implementation.",
        "journal": [
            {"type": JOURNAL_REMARK, "title": "Be kind, it is their first PR",
             "body": "Suggest the cancellation test as a snippet, not as a demand."},
            {"type": JOURNAL_FINDING, "title": "The bench in the PR runs on a warm cache",
             "body": "Numbers will differ on a cold start; ask for both."},
        ],
    },
    {
        "title": "Contributor guide",
        "description": "CONTRIBUTING.md answers how to run the tests and what a PR needs",
        "group": "Community",
        "type": TYPE_SIMPLE,
        "status": STATUS_BACKLOG,
        "priority": PRIORITY_NORMAL,
    },
]

ARCHIVED_TASKS = [
    {
        "title": "Migrate the landing page to the new CMS",
        "description": "Never finished — the project closed first",
        "group": "Old backlog",
        "type": TYPE_STANDARD,
        "status": STATUS_IN_PROGRESS,
        "priority": PRIORITY_NORMAL,
        "plan": "Pages one by one, redirects at the end.",
    },
    {
        "title": "Turn off the old mail server",
        "description": "Mail goes through the provider",
        "group": "Old backlog",
        "type": TYPE_SIMPLE,
        "status": STATUS_DONE,
        "priority": PRIORITY_LOW,
    },
]

# Codexes are not per workspace — one set for the whole installation, mounted by the workspaces
# above. The trees reach the depth limit (codex / note / note / note) on purpose, carry a deleted
# note and a deleted codex for the trash, and one codex has no notes at all.
# Notes go top to bottom in the order given; ``deleted`` sends a leaf note to the trash.
CODEXES = [
    {
        "segment": "python",
        "title": "Python backend",
        "description": "Открывать перед любой правкой Python-кода: стиль, асинхронность, тесты, слои.",
        "color": "blue",
        "icon": "code",
        "body": md("""
            Правила для бэкенда на Python 3.12+, FastAPI и SQLAlchemy async.

            - Код читается сверху вниз: сначала публичная функция, ниже её помощники.
            - Имя объясняет «что», комментарий — только «почему».
            - Ошибка правила — `ValueError` с числами, до первой записи в базу.
            - Ни одного `print` в `src/` — только логгеры модуля.
        """),
        "notes": [
            {
                "segment": "style",
                "title": "Стиль",
                "description": "Имена, импорты, типы — то, что ловится на ревью первым",
                "body": "Форматирование делает `ruff format`, спорить о нём не нужно. Здесь — то, что форматтер не решит.",
                "children": [
                    {
                        "segment": "naming",
                        "title": "Имена",
                        "description": "Как называть функции CRUD, константы и булевы поля",
                        "body": md("""
                            | Что | Как | Пример |
                            | --- | --- | --- |
                            | CRUD | `<сущность>_<глагол>` | `task_create`, `mount_list` |
                            | Булево поле | утверждение | `agent_can_edit`, не `edit_flag` |
                            | Константа лимита | `<ПОЛЕ>_MAX` | `TITLE_MAX` |

                            Сокращения — только общепринятые: `s` для сессии, `row` для ORM-строки.
                        """),
                    },
                    {
                        "segment": "imports",
                        "title": "Импорты",
                        "description": "Абсолютные от src, модуль целиком для CRUD",
                        "body": md("""
                            ```python
                            from src.modules.tasks.crud import task as task_crud

                            await task_crud.task_get(code)
                            ```

                            Импорт модуля, а не функции: по месту вызова видно, чей это CRUD.
                        """),
                    },
                    {
                        "segment": "typing",
                        "title": "Типы",
                        "description": "Аннотации обязательны в сигнатурах, в теле — по необходимости",
                        "body": "`X | None` вместо `Optional[X]`, встроенные `list[str]` вместо `List[str]`.",
                    },
                ],
            },
            {
                "segment": "async",
                "title": "Асинхронность и сессии",
                "description": "write_scope, session_scope и почему не держать сессию через await к сети",
                "body": md("""
                    Читающий код открывает `session_scope()`, пишущий — `write_scope()`: на SQLite это
                    `BEGIN IMMEDIATE`, и две записи не дерутся за блокировку посреди транзакции.

                    Никогда не ждать сеть внутри открытой пишущей сессии — база заблокирована всё это время.
                """),
                "children": [
                    {
                        "segment": "locks",
                        "title": "Блокировки",
                        "description": "Когда нужен pg_advisory_xact_lock",
                        "body": "Структурные записи дерева сериализуются: на PostgreSQL — один advisory-lock на транзакцию.",
                    },
                ],
            },
            {
                "segment": "test",
                "title": "Тесты",
                "description": "Маркеры, фикстуры, фабрики — перед написанием любого теста",
                "body": "Каждый тест несёт ровно один маркер типа: `pure`, `db`, `heavy` или `live`.",
                "children": [
                    {
                        "segment": "markers",
                        "title": "Маркеры",
                        "description": "Что значит каждый и что запускается по умолчанию",
                        "body": md("""
                            - `pure` — ни базы, ни сети;
                            - `db` — SQLite в памяти, схема из моделей;
                            - `heavy` — настоящие миграции, только PostgreSQL;
                            - `live` — внешние сервисы.

                            По умолчанию идут `pure` + `db`.
                        """),
                    },
                    {
                        "segment": "factories",
                        "title": "Фабрики",
                        "description": "Как собирать тестовые данные без копипасты",
                        "body": "Фабрика — функция модульного `conftest.py`, возвращает ORM-строку и принимает только то, что тест проверяет.",
                        "children": [
                            {
                                "segment": "naming",
                                "title": "Имена фабрик",
                                "description": "make_<сущность>, без префикса модуля",
                                "body": "`make_task`, `make_codex` — модуль и так понятен из пути к conftest.",
                            },
                            {
                                "segment": "defaults",
                                "title": "Значения по умолчанию",
                                "description": "Что фабрика заполняет сама",
                                "body": "Заголовок — `f\"{сущность} {n}\"`, остальное пустое: тест, которому важно поле, задаёт его явно.",
                            },
                        ],
                    },
                    {
                        "segment": "fixtures-old",
                        "title": "Старые фикстуры (устарело)",
                        "description": "Заменено фабриками",
                        "body": "Глобальные фикстуры с готовыми наборами данных больше не используются.",
                        "deleted": True,
                    },
                ],
            },
            {
                "segment": "layers",
                "title": "Уровни модулей",
                "description": "Кто кого может импортировать",
                "body": md("""
                    1. `workspace`, `notes` — уровень 1, не импортируют прикладные модули.
                    2. `tasks`, `codex` — уровень 2.
                    3. `workbench` — уровень 3, вся поверхность агента.

                    Проверяется тестом `tests/apps/test_python_layer_boundaries.py`.
                """),
            },
        ],
    },
    {
        "segment": "vue",
        "title": "Vue frontend",
        "description": "Компоненты, сторы, i18n и Vuetify — перед правкой web/src.",
        "color": "green",
        "icon": "palette",
        "body": md("""
            Vue 3 + Vuetify + Pinia + TypeScript. Сборка `pnpm --dir web build` начинается с `vue-tsc`,
            ошибка типов валит сборку.

            Проверка в браузере обязательна: реальные клавиши, реальный указатель, вычисленные значения.
        """),
        "notes": [
            {
                "segment": "components",
                "title": "Компоненты",
                "description": "Когда выносить компонент и куда",
                "body": "Компонент живёт в фиче, пока его не использует вторая фича — тогда он переезжает в `components/`.",
                "children": [
                    {
                        "segment": "action-menu",
                        "title": "Меню действий строки",
                        "description": "Только ActionMenu, никогда голый VMenu",
                        "body": "Пункты — массив, горячие клавиши — буквы: C отмена, D удалить, E правка.",
                    },
                ],
            },
            {
                "segment": "stores",
                "title": "Сторы",
                "description": "Pinia: что держит стор, что — компонент",
                "body": "Стор считает раскладку, страница только рисует. Загрузка данных — в `onActivated`, не в `onMounted`.",
            },
            {
                "segment": "i18n",
                "title": "Переводы",
                "description": "Пространство имён = имя папки фичи",
                "body": "Символы `@` и `|` в тексте сообщения экранировать: `{'@'}`, `{'|'}`.",
            },
        ],
    },
    {
        "segment": "sql",
        "title": "SQL и миграции",
        "description": "Переносимость SQLite ↔ PostgreSQL, Alembic, порядок колонок.",
        "color": "teal",
        "icon": "database",
        "body": md("""
            Миграции обязаны проходить на обоих провайдерах. Одна таблица — одна миграция.
            Хвост любой таблицы: `deleted_at`, `created_at`, `updated_at`.
        """),
        "notes": [
            {
                "segment": "portable",
                "title": "Переносимые типы",
                "description": "Чем SQLite отличается и где это кусается",
                "body": md("""
                    - `lower()` на SQLite знает только ASCII — кириллицу сворачивать в Python.
                    - `VARCHAR(n)` SQLite не проверяет — лимит держит сервис.
                    - Частичные уникальные индексы работают на обоих.
                """),
            },
            {
                "segment": "alembic",
                "title": "Alembic",
                "description": "Имена ревизий, ветки модулей, depends_on",
                "body": "Ревизия — `<abbr>m_<NNN>_<описание>`, не длиннее 32 символов. Зависимость — на ревизию, создающую цель FK, а не на голову цепочки.",
            },
        ],
    },
    {
        "segment": "git",
        "title": "Git и релизы",
        "description": "Коммиты, ветки, теги — перед любым коммитом.",
        "color": "orange",
        "icon": "git-branch",
        "body": md("""
            Коммит — одна строка по-английски, в повелительном наклонении после префикса модуля:
            `codex: mount order survives a switch-off`.

            Добавлять файлы по одному. Никаких `git add -A`.
        """),
        "notes": [
            {
                "segment": "commits",
                "title": "Коммиты",
                "description": "Формат сообщения и что в коммит не попадает",
                "body": "Не попадают: `.env`, `runtime/*`, `node_modules/`. Попадает собранный `web/dist`.",
            },
            {
                "segment": "release",
                "title": "Релиз",
                "description": "Версия, дата, тег",
                "body": "Версия и дата — в `pyproject.toml`, копии в `web/package.json` и `uv.lock` сверяет тест.",
            },
        ],
    },
    {
        "segment": "writing",
        "title": "Тексты и документация",
        "description": "Как писать бриф, журнал, README — перед любым текстом для человека.",
        "color": "violet",
        "icon": "feather",
        "body": md("""
            Пиши коротко: одно предложение — одна мысль. Без «данный», «осуществить»,
            «в рамках». Сначала вывод, потом подробности.
        """),
        "notes": [
            {
                "segment": "brief",
                "title": "Бриф задачи",
                "description": "Цель, контекст, ограничения, критерии",
                "body": "Критерий проверяем командой или наблюдением. «Работает хорошо» — не критерий.",
            },
            {
                "segment": "journal",
                "title": "Журнал",
                "description": "Решение, факт, находка, замечание — что когда",
                "body": md("""
                    | Тип | Когда |
                    | --- | --- |
                    | Решение | выбрали из нескольких путей |
                    | Факт | измерили или проверили |
                    | Находка | увидели проблему вне задачи |
                    | Замечание | сказал человек |
                """),
            },
        ],
    },
    {
        "segment": "security",
        "title": "Безопасность",
        "description": "Секреты, зависимости, внешние данные.",
        "color": "red",
        "icon": "shield-lock",
        "body": "Секрет никогда не попадает в лог, в коммит и в текст задачи. Ключи — только из `.env`.",
        "notes": [
            {
                "segment": "secrets",
                "title": "Секреты",
                "description": "Где хранить, как ротировать",
                "body": "Утёкший ключ ротируется сразу, без выяснения, видел ли его кто-то.",
            },
        ],
    },
    # A codex with no notes: the tree of a codex that has only its rules.
    {
        "segment": "shell",
        "title": "Shell-скрипты",
        "description": "bash в tools/ и run.sh.",
        "color": "slate",
        "icon": "tools",
        "body": "`set -euo pipefail` в первой строке после шебанга. Комментарий — над командой, не в конце строки.",
        "notes": [],
    },
    {
        "segment": "jquery",
        "title": "jQuery (устарело)",
        "description": "Остался от старого фронтенда — exercises the deleted codexes.",
        "color": "slate",
        "icon": "archive",
        "body": "Не использовать.",
        "notes": [
            {"segment": "plugins", "title": "Плагины", "description": "", "body": "Список больше не поддерживается."},
        ],
        "deleted": True,
    },
]


# ── assembly ──────────────────────────────────────────────────────────────────


# Every key a task spec may carry. A key outside it is a typo or a renamed field — ``body`` once
# quietly seeded empty plans — and fails the seeding instead of vanishing.
TASK_SPEC_KEYS = frozenset({
    "title", "description", "context", "constraints", "criteria", "plan", "progress", "result",
    "type", "status", "priority", "group", "created_by", "deadline_days", "deleted",
    "stages", "journal", "notes", "children",
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
        entry = await journal_crud.journal_create(
            task_code=task.code,
            type=entry_spec["type"],
            title=entry_spec["title"],
            body=entry_spec.get("body", ""),
            resolution=entry_spec.get("resolution", "") if entry_spec["type"] == JOURNAL_FACT else "",
        )
        if entry_spec.get("resolution") and entry_spec["type"] != JOURNAL_FACT:
            await journal_crud.journal_resolve(entry.code, entry_spec["resolution"])

    for note_spec in spec.get("notes", []):
        await task_note_crud.task_note_add(
            task_code=task.code,
            title=note_spec["title"],
            description=note_spec.get("description", ""),
            body=note_spec.get("body", ""),
        )

    for child in spec.get("children", []):
        await seed_task(workspace_code=workspace_code, spec=child, groups=groups, parent_code=task.code)

    if spec.get("deleted"):
        await task_crud.task_delete(task.code)

    return task.code


async def free_codex_segment(segment: str) -> str:
    """``segment``, or ``segment-2``, ``segment-3``… — a codex segment is unique across the installation, and
    a second run must not collide with the first or with a person's own codex."""
    candidate, n = segment, 1
    while await codex_crud.codex_get_by_segment(candidate) is not None:
        n += 1
        candidate = f"{segment}-{n}"
    return candidate


async def seed_codex_notes(parent_code: str, specs: list[dict]) -> int:
    """A level of a codex tree and everything under it; returns the number of notes written."""
    count = 0
    for spec in specs:
        note = await codex_note_crud.note_create(
            parent_code=parent_code,
            segment=spec["segment"],
            title=spec["title"],
            description=spec.get("description", ""),
            body=spec.get("body", ""),
        )
        count += 1 + await seed_codex_notes(note.code, spec.get("children", []))
        if spec.get("deleted"):
            await codex_note_crud.note_delete(note.code)
    return count


async def seed_codexes(specs: list[dict]) -> tuple[dict[str, str], list[dict]]:
    """Every codex with its tree. Returns spec segment → code (live ones only) and report rows."""
    codes: dict[str, str] = {}
    report = []
    for spec in specs:
        codex = await codex_crud.codex_create(
            segment=await free_codex_segment(spec["segment"]),
            title=spec["title"],
            description=spec["description"],
            body=spec["body"],
            color=spec["color"],
            icon=spec["icon"],
        )
        notes = await seed_codex_notes(codex.code, spec["notes"])
        if spec.get("deleted"):
            await codex_crud.codex_delete(codex.code)
        else:
            codes[spec["segment"]] = codex.code
        report.append({"codex": codex.title, "code": codex.code, "segment": codex.segment, "notes": notes,
                       "deleted": bool(spec.get("deleted"))})
    return codes, report


async def seed_workspace(spec: dict, tasks: list[dict], codexes: dict[str, str]) -> dict:
    """A whole workspace: card, groups, tasks, mounted codexes. Returns counters for the report."""
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

    for mount_spec in spec.get("codexes", []):
        # Under ``--bulk`` a hand-written codex may not exist yet — that mount is skipped.
        codex_code = codexes.get(mount_spec["segment"])
        if codex_code is None:
            continue
        await mount_crud.mount_add(
            codex_code, workspace.code, agent_can_edit=mount_spec.get("agent_can_edit", True)
        )
        if mount_spec.get("off"):
            await mount_crud.mount_remove(codex_code, workspace.code)

    rows = await task_crud.task_list_by_workspace(workspace.code, include_deleted=True)
    notes = 0
    for row in rows:
        notes += len(await task_note_crud.task_note_list(row.code))

    # Last: a deleted workspace refuses new mounts, so it fills up first and goes to the trash after.
    if spec.get("deleted"):
        await workspace_crud.workspace_delete(workspace.code)

    return {"workspace": workspace.title, "code": workspace.code, "groups": len(groups), "tasks": len(rows),
            "notes": notes, "codexes": len(spec.get("codexes", [])), "deleted": bool(spec.get("deleted"))}


async def existing_codexes(specs: list[dict]) -> dict[str, str]:
    """Spec segment → code of the live codex already holding that segment — what ``--bulk`` mounts
    instead of seeding the hand-written codexes a second time."""
    found = {}
    for spec in specs:
        row = await codex_crud.codex_get_by_segment(spec["segment"])
        if row is not None:
            found[spec["segment"]] = row.code
    return found


async def main(small: bool, bulk_only: bool) -> int:
    config = Config()
    target = config.db_path or config.db_name or "default"
    print(f"database: {config.db_provider} → {target}")

    tasks_by_workspace = [DEV_TASKS, PERSONAL_TASKS, CLIENT_TASKS, OSS_TASKS, [], ARCHIVED_TASKS]
    plan = list(zip(WORKSPACES, tasks_by_workspace, strict=True))
    codex_specs = list(CODEXES)
    if small:
        plan = plan[:1]
    else:
        writer = bulk.Writer()
        if bulk_only:
            plan, codex_specs = [], []
        codex_specs.append(bulk.handbook_codex(writer))
        plan += bulk.workspaces(writer)

    await init_database(config)
    try:
        # Read before seeding: the handbook seeded below must not be mistaken for an older one.
        mounted = await existing_codexes(CODEXES) if bulk_only else {}
        codexes, codex_report = await seed_codexes(codex_specs)
        codexes = mounted | codexes
        report = [await seed_workspace(spec, tasks, codexes) for spec, tasks in plan]
    finally:
        await close_database()

    print("\ncodexes:")
    for row in codex_report:
        trash = " — in the trash" if row["deleted"] else ""
        print(f"  {row['codex']} ({row['code']}, /{row['segment']}): notes {row['notes']}{trash}")
    print("\nworkspaces:")
    for row in report:
        trash = " — in the trash" if row["deleted"] else ""
        print(f"  {row['workspace']} ({row['code']}): groups {row['groups']}, tasks {row['tasks']}, "
              f"task notes {row['notes']}, codexes {row['codexes']}{trash}")
    print('\nremove the demo from the interface: "Workspaces" → delete → "Delete forever"; '
          '"Codex" → delete for the codexes.')
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Demo data: workspaces, groups, tasks with notes, codexes with their trees and mounts."
    )
    scope = parser.add_mutually_exclusive_group()
    scope.add_argument("--small", action="store_true", help="only the single development workspace")
    scope.add_argument("--bulk", action="store_true",
                       help="only the long texts and the volume: the handbook codex and two workspaces, "
                            "mounting the hand-written codexes already in the database")
    args = parser.parse_args()
    raise SystemExit(asyncio.run(main(args.small, args.bulk)))
