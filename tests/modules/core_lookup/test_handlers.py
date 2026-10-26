"""The real handlers through the executor: every registered prefix answers with its title,
description and page, settles its own misses in the agreed order, honours the workspace filter
its own way, and reads a batch in a fixed number of SQL statements.

Rows are written straight through the ORM: what is under test is how the handlers read them, not
the services that write them.
"""

from __future__ import annotations

from datetime import datetime

import pytest
from fastapi import FastAPI
from sqlalchemy import event

from src.core.config import Config
from src.core.database import close_database, init_database, write_scope
from src.core.database.runtime import Base
from src.modules.core_lookup import engine
from src.modules.core_lookup.registry import registered_types

pytestmark = pytest.mark.db

HERE = "WORKSPACE@AAAAAAAAAA"
THERE = "WORKSPACE@BBBBBBBBBB"
# Naive UTC, the way `utc_now()` stores it: PostgreSQL refuses an aware value for the column.
DELETED_AT = datetime(2026, 1, 1)


def _code(n: int) -> str:
    return f"{n:010X}"


@pytest.fixture
async def db(config: Config):
    db_engine = await init_database(config)
    import src.modules.codex.models  # noqa: F401
    import src.modules.notes.models  # noqa: F401
    import src.modules.tasks.models  # noqa: F401
    import src.modules.workspace.models  # noqa: F401

    async with db_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    try:
        yield db_engine
    finally:
        await close_database()


@pytest.fixture
def registered(config: Config) -> None:
    """The lookup types exactly as the assembled app registers them."""
    from src.apps.app.modules import build_modules

    app = FastAPI()
    for module in build_modules():
        module.configure(app, config)


async def _add(*rows) -> None:
    async with write_scope() as s:
        for row in rows:
            s.add(row)
            await s.flush()


async def _world() -> None:
    """Two workspaces, each type present in both, so a filter that is ignored shows.

    Here: a group, a task with a stage, an entry and a note, a deleted task holding a stage, an
    entry and a live note, a deleted group, a deleted note on a live task, a mounted codex with a
    live and a deleted note. There: a group, a task with a stage, an entry and a note, a deleted
    task, a codex mounted only there. Nowhere: a codex mounted nowhere, a codex whose mount here
    is switched off (with a note), a document no task holds."""
    from src.modules.codex.models import Codex, CodexMount, CodexNote
    from src.modules.notes.models.note import Note
    from src.modules.tasks.models import (
        TasksGroup,
        TasksJournal,
        TasksNote,
        TasksStage,
        TasksTask,
    )
    from src.modules.workspace.models.workspace import Workspace

    await _add(
        Workspace(code="AAAAAAAAAA", title="Here", description="the working one"),
        Workspace(code="BBBBBBBBBB", title="There"),
        Workspace(code="CCCCCCCCCC", title="Gone", deleted_at=DELETED_AT),
        TasksGroup(code="0000000001", workspace_code="AAAAAAAAAA", title="Group", description="g"),
        TasksTask(code="0000000002", workspace_code="AAAAAAAAAA", title="Task", description="t"),
        TasksTask(code="0000000003", workspace_code="BBBBBBBBBB", title="Foreign task"),
        TasksTask(
            code="0000000004", workspace_code="AAAAAAAAAA", title="Old", deleted_at=DELETED_AT
        ),
        TasksTask(
            code="0000000005", workspace_code="BBBBBBBBBB", title="Foreign old", deleted_at=DELETED_AT
        ),
        TasksStage(code="0000000006", task_code="0000000002", number=1, title="Stage", description="s"),
        TasksStage(code="0000000007", task_code="0000000004", number=1, title="Orphaned stage"),
        TasksJournal(code="0000000008", task_code="0000000002", type="fact", title="Entry", body="b"),
        Note(code="0000000009", title="Note", description="n"),
        Note(code="000000000A", title="Loose note"),
        Codex(code="000000000B", segment="python", title="Python", description="rules"),
        Codex(code="000000000C", segment="vue", title="Vue"),
        Codex(code="000000000D", segment="off", title="Switched off"),
        Codex(code="000000000F", segment="there", title="Theirs"),
        TasksGroup(code="0000000010", workspace_code="BBBBBBBBBB", title="Foreign group"),
        TasksStage(code="0000000011", task_code="0000000003", number=1, title="Foreign stage"),
        TasksJournal(code="0000000012", task_code="0000000003", type="fact", title="Foreign entry"),
        Note(code="0000000013", title="Foreign note"),
        TasksGroup(
            code="0000000014", workspace_code="AAAAAAAAAA", title="Old group", deleted_at=DELETED_AT
        ),
        TasksJournal(code="0000000015", task_code="0000000004", type="fact", title="Old entry"),
        Note(code="0000000016", title="Deleted note", deleted_at=DELETED_AT),
        Note(code="0000000017", title="Note of an old task"),
    )
    await _add(
        TasksNote(note_code="0000000009", task_code="0000000002", sort=1),
        TasksNote(note_code="0000000013", task_code="0000000003", sort=1),
        TasksNote(note_code="0000000016", task_code="0000000002", sort=2),
        TasksNote(note_code="0000000017", task_code="0000000004", sort=1),
        CodexNote(code="000000000E", codex_code="000000000B", segment="tests", title="Tests"),
        CodexNote(code="0000000018", codex_code="000000000D", segment="off-note", title="Off note"),
        CodexNote(
            code="0000000019",
            codex_code="000000000B",
            segment="gone",
            title="Gone note",
            deleted_at=DELETED_AT,
        ),
        CodexMount(codex_code="000000000B", workspace_code="AAAAAAAAAA", sort=1),
        CodexMount(codex_code="000000000D", workspace_code="AAAAAAAAAA", sort=2, enabled=False),
        CodexMount(codex_code="000000000F", workspace_code="BBBBBBBBBB", sort=1),
    )


async def _preview(codes: list[str], workspace: str | None = HERE) -> dict[str, dict]:
    filters = {"workspace": workspace} if workspace else {}
    return {r.code: r.model_dump() for r in await engine.preview(codes, filters)}


def _error(record: dict) -> str | None:
    return record["error"]["code"] if record["error"] else None


def test_the_assembled_app_registers_every_prefix(registered):
    words = {kind.prefix for kind in registered_types()}

    assert words == {
        "WORKSPACE",
        "TASK",
        "TASKGROUP",
        "STAGE",
        "JOURNAL",
        "NOTE",
        "CODEX",
        "FILE",
        "IMAGE",
    }


async def test_every_type_answers_with_its_title_description_and_page(db, registered):
    await _world()

    got = await _preview(
        [
            "WORKSPACE@AAAAAAAAAA",
            "TASKGROUP@0000000001",
            "TASK@0000000002",
            "STAGE@0000000006",
            "JOURNAL@0000000008",
            "NOTE@0000000009",
            "CODEX@000000000B",
            "CODEX@000000000E",
        ]
    )

    assert {code: (r["title"], r["description"], r["link"]) for code, r in got.items()} == {
        "WORKSPACE@AAAAAAAAAA": ("Here", "the working one", "/workspaces"),
        "TASKGROUP@0000000001": ("Group", "g", "/tasks/groups"),
        "TASK@0000000002": ("Task", "t", "/tasks/task/TASK@0000000002"),
        "STAGE@0000000006": ("Stage", "s", "/tasks/task/TASK@0000000002"),
        "JOURNAL@0000000008": ("Entry", "", "/tasks/task/TASK@0000000002"),
        "NOTE@0000000009": ("Note", "n", "/tasks/task/TASK@0000000002/note/NOTE@0000000009"),
        "CODEX@000000000B": ("Python", "rules", "/codex/materials/CODEX@000000000B"),
        "CODEX@000000000E": ("Tests", "", "/codex/materials/CODEX@000000000E"),
    }
    assert all(r["error"] is None for r in got.values())


@pytest.mark.parametrize(
    ("code", "reason"),
    [
        ("TASK@00000000FF", "not_found"),
        ("STAGE@00000000FF", "not_found"),
        ("JOURNAL@00000000FF", "not_found"),
        ("CODEX@00000000FF", "not_found"),
        ("WORKSPACE@00000000FF", "not_found"),
        # A document no task holds has no workspace and no page.
        ("NOTE@000000000A", "not_found"),
        # Every type bound to a workspace refuses the other one — each by its own route to it.
        ("TASK@0000000003", "foreign_scope"),
        ("TASKGROUP@0000000010", "foreign_scope"),
        ("STAGE@0000000011", "foreign_scope"),
        ("JOURNAL@0000000012", "foreign_scope"),
        ("NOTE@0000000013", "foreign_scope"),
        ("CODEX@000000000F", "foreign_scope"),
        # Deleted elsewhere: the deletion is not told across the boundary.
        ("TASK@0000000005", "foreign_scope"),
        ("TASK@0000000004", "deleted"),
        ("TASKGROUP@0000000014", "deleted"),
        # A stage and an entry are deleted only through their task.
        ("STAGE@0000000007", "deleted"),
        ("JOURNAL@0000000015", "deleted"),
        # A note is deleted by itself or with the task that holds it.
        ("NOTE@0000000016", "deleted"),
        ("NOTE@0000000017", "deleted"),
        ("WORKSPACE@CCCCCCCCCC", "deleted"),
        # A codex is visible through a live, switched-on mount only — and so are its notes.
        ("CODEX@000000000C", "foreign_scope"),
        ("CODEX@000000000D", "foreign_scope"),
        ("CODEX@0000000018", "foreign_scope"),
        # A codex note is deleted by itself while its codex lives on.
        ("CODEX@0000000019", "deleted"),
    ],
)
async def test_a_miss_carries_its_reason_and_nothing_else(db, registered, code, reason):
    await _world()

    [record] = (await _preview([code])).values()

    assert _error(record) == reason
    assert (record["title"], record["description"], record["link"]) == ("", "", "")


async def test_without_a_workspace_filter_nothing_is_narrowed(db, registered):
    await _world()

    got = await _preview(["TASK@0000000003", "CODEX@000000000C"], workspace=None)

    assert [_error(r) for r in got.values()] == [None, None]


async def test_the_foreign_ones_are_seen_from_their_own_workspace(db, registered):
    """Positive control for the foreign rows above: they are refused for where they are asked from,
    not because they are unreadable."""
    await _world()

    got = await _preview(
        [
            "TASK@0000000003",
            "TASKGROUP@0000000010",
            "STAGE@0000000011",
            "JOURNAL@0000000012",
            "NOTE@0000000013",
            "CODEX@000000000F",
        ],
        workspace=THERE,
    )

    assert {code: (r["title"], _error(r)) for code, r in got.items()} == {
        "TASK@0000000003": ("Foreign task", None),
        "TASKGROUP@0000000010": ("Foreign group", None),
        "STAGE@0000000011": ("Foreign stage", None),
        "JOURNAL@0000000012": ("Foreign entry", None),
        "NOTE@0000000013": ("Foreign note", None),
        "CODEX@000000000F": ("Theirs", None),
    }


async def test_a_workspace_nobody_has_narrows_everything_away_but_workspaces(db, registered):
    await _world()

    got = await _preview(["TASK@0000000002", "WORKSPACE@AAAAAAAAAA"], workspace="WORKSPACE@FFFFFFFFFF")

    assert [_error(r) for r in got.values()] == ["foreign_scope", None]


async def test_a_workspace_is_shown_whichever_one_the_person_works_in(db, registered):
    await _world()

    [record] = (await _preview(["WORKSPACE@BBBBBBBBBB"])).values()

    assert (record["title"], _error(record)) == ("There", None)


async def test_a_deleted_codex_takes_its_notes_along(db, registered):
    await _world()
    from src.modules.codex.models import Codex

    async with write_scope() as s:
        (await s.get(Codex, "000000000B")).deleted_at = DELETED_AT

    got = await _preview(["CODEX@000000000B", "CODEX@000000000E"])

    assert [_error(r) for r in got.values()] == ["deleted", "deleted"]


async def test_the_retired_group_word_still_resolves(db, registered):
    await _world()

    [record] = (await _preview(["GROUP@0000000001"])).values()

    assert (record["code"], record["title"]) == ("GROUP@0000000001", "Group")


SCALED = 25


async def _scaled_world() -> dict[str, list[str]]:
    """``SCALED`` live rows of every type here, codes by type word."""
    from src.modules.codex.models import CodexNote
    from src.modules.notes.models.note import Note
    from src.modules.tasks.models import TasksGroup, TasksJournal, TasksNote, TasksStage, TasksTask
    from src.modules.workspace.models.workspace import Workspace

    n_range = range(SCALED)
    await _add(
        *(Workspace(code=_code(0x600 + n), title=f"W{n}") for n in n_range),
        *(TasksTask(code=_code(0x100 + n), workspace_code="AAAAAAAAAA", title=f"T{n}") for n in n_range),
        *(TasksGroup(code=_code(0x400 + n), workspace_code="AAAAAAAAAA", title=f"G{n}") for n in n_range),
        *(Note(code=_code(0x500 + n), title=f"N{n}") for n in n_range),
    )
    await _add(
        *(TasksStage(code=_code(0x200 + n), task_code=_code(0x100 + n), number=1, title=f"S{n}") for n in n_range),
        *(
            TasksJournal(code=_code(0x300 + n), task_code=_code(0x100 + n), type="fact", title=f"J{n}")
            for n in n_range
        ),
        *(TasksNote(note_code=_code(0x500 + n), task_code=_code(0x100 + n), sort=1) for n in n_range),
        *(
            CodexNote(code=_code(0x700 + n), codex_code="000000000B", segment=f"n{n}", title=f"C{n}")
            for n in n_range
        ),
    )
    bases = {"TASK": 0x100, "STAGE": 0x200, "JOURNAL": 0x300, "TASKGROUP": 0x400, "NOTE": 0x500}
    bases |= {"WORKSPACE": 0x600, "CODEX": 0x700}
    return {word: [f"{word}@{_code(base + n)}" for n in n_range] for word, base in bases.items()}


async def test_the_sql_count_does_not_grow_with_the_batch(db, registered):
    """A body quoting every type many times costs what one code of each type does."""
    await _world()
    by_type = await _scaled_world()

    async def statements(codes: list[str]) -> int:
        seen: list[str] = []

        def count(conn, cursor, statement, *args):
            if statement.lstrip().upper().startswith("SELECT"):
                seen.append(statement)

        event.listen(db.sync_engine, "before_cursor_execute", count)
        try:
            await _preview(codes)
        finally:
            event.remove(db.sync_engine, "before_cursor_execute", count)
        return len(seen)

    every = [code for codes in by_type.values() for code in codes]
    one = await statements([codes[0] for codes in by_type.values()])
    many = await statements(every)
    answered = await _preview(every)

    assert 0 < one == many
    assert len(answered) == len(by_type) * SCALED
    assert [code for code, record in answered.items() if record["error"]] == []
