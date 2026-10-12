"""The executor on fake handlers: a record for every code, one call per type, the handler's own
verdicts passed through, and a silent or failing handler turned into ``failed`` with a log line.
"""

from __future__ import annotations

import pytest

from src.modules.core_lookup import engine
from src.modules.core_lookup.registry import (
    LookupType,
    Miss,
    Preview,
    register_type,
    registered_types,
    type_for,
)

pytestmark = pytest.mark.pure


class Recorder:
    """A handler that answers from a fixed table and remembers how it was called."""

    def __init__(self, table: dict[str, Preview | Miss]):
        self.table = table
        self.calls: list[tuple[list[str], dict]] = []

    async def __call__(self, codes, filters):
        self.calls.append((codes, dict(filters)))
        return {code: self.table[code] for code in codes if code in self.table}


class FakeLog:
    def __init__(self):
        self.errors: list[str] = []

    def error(self, msg, *args, **kwargs):
        self.errors.append(msg % args)

    def exception(self, msg, *args, **kwargs):
        self.errors.append(msg % args)


@pytest.fixture
def log(monkeypatch) -> FakeLog:
    fake = FakeLog()
    monkeypatch.setattr(engine, "_LOG", fake)
    return fake


def _error(record) -> str | None:
    return record.error.code if record.error else None


async def test_every_code_gets_a_record_in_request_order_with_duplicates_folded():
    tasks = Recorder({"AA": Preview("Task A", "about A", "/tasks/task/TASK@AA")})
    notes = Recorder({"BB": Preview("Note B")})
    register_type(LookupType("TASK", tasks))
    register_type(LookupType("NOTE", notes))

    records = await engine.preview(["note@bb", "TASK@AA", "NOTE@BB"], {})

    assert [r.code for r in records] == ["NOTE@BB", "TASK@AA"]
    assert (records[1].title, records[1].description, records[1].link) == (
        "Task A",
        "about A",
        "/tasks/task/TASK@AA",
    )
    assert records[1].error is None


async def test_one_call_per_type_with_bare_codes_and_the_filters_as_they_came():
    tasks = Recorder({"AA": Preview("A"), "BB": Preview("B")})
    register_type(LookupType("TASK", tasks))

    await engine.preview(["TASK@AA", "TASK@BB"], {"workspace": "WORKSPACE@CC"})

    assert tasks.calls == [(["AA", "BB"], {"workspace": "WORKSPACE@CC"})]


async def test_the_handlers_verdicts_pass_through():
    tasks = Recorder({"AA": Miss.NOT_FOUND, "BB": Miss.FOREIGN_SCOPE, "CC": Miss.DELETED})
    register_type(LookupType("TASK", tasks))

    records = await engine.preview(["TASK@AA", "TASK@BB", "TASK@CC"], {})

    assert [_error(r) for r in records] == ["not_found", "foreign_scope", "deleted"]
    assert all((r.title, r.description, r.link) == ("", "", "") for r in records)
    assert all(r.error.message for r in records)


@pytest.mark.parametrize("code", ["STAGE@AA", "TASK", "TASK@", "TASK@xyz", "@AA", "TASK@AA@BB"])
async def test_an_unknown_prefix_or_a_malformed_code_is_not_found_without_asking(code):
    tasks = Recorder({"AA": Preview("A")})
    register_type(LookupType("TASK", tasks))

    [record] = await engine.preview([code], {})

    assert _error(record) == "not_found"
    assert tasks.calls == []


async def test_a_code_the_handler_skipped_is_failed_and_logged(log):
    tasks = Recorder({"AA": Preview("A")})
    register_type(LookupType("TASK", tasks))

    records = await engine.preview(["TASK@AA", "TASK@BB"], {})

    assert [_error(r) for r in records] == [None, "failed"]
    assert log.errors == ["lookup: the TASK@ handler gave no answer for TASK@BB"]


async def test_a_raising_handler_fails_its_own_codes_only(log):
    async def broken(codes, filters):
        raise RuntimeError("boom")

    register_type(LookupType("TASK", broken))
    register_type(LookupType("NOTE", Recorder({"BB": Preview("B")})))

    records = await engine.preview(["TASK@AA", "NOTE@BB"], {})

    assert [_error(r) for r in records] == ["failed", None]
    assert len(log.errors) == 2


async def test_an_alias_is_answered_by_its_type_under_the_code_as_asked():
    groups = Recorder({"AA": Preview("Group")})
    register_type(LookupType("TASKGROUP", groups, aliases=("GROUP",)))

    [record] = await engine.preview(["GROUP@AA"], {})

    assert (record.code, record.title) == ("GROUP@AA", "Group")
    assert type_for("GROUP") is type_for("TASKGROUP")
    assert len(registered_types()) == 1


async def test_codes_come_back_canonical_and_spellings_of_one_code_fold_into_one_record():
    """The record carries the canonical code — upper case, trimmed — not the spelling asked: the
    interface sends canonical codes and keys its cache by them, an agent may send any case."""
    tasks = Recorder({"AA": Preview("A")})
    register_type(LookupType("TASK", tasks))

    records = await engine.preview(["task@aa", " TASK@AA ", "TASK@AA"], {})

    assert [r.code for r in records] == ["TASK@AA"]
    assert tasks.calls == [(["AA"], {})]


async def test_an_alias_and_its_type_share_one_handler_call():
    groups = Recorder({"AA": Preview("Group")})
    register_type(LookupType("TASKGROUP", groups, aliases=("GROUP",)))

    records = await engine.preview(["GROUP@AA", "TASKGROUP@AA"], {})

    assert [(r.code, r.title) for r in records] == [("GROUP@AA", "Group"), ("TASKGROUP@AA", "Group")]
    assert groups.calls == [(["AA"], {})]


async def test_no_codes_ask_no_handler():
    tasks = Recorder({})
    register_type(LookupType("TASK", tasks))

    assert await engine.preview([], {"workspace": "WORKSPACE@CC"}) == []
    assert tasks.calls == []


async def test_an_answer_for_a_code_not_asked_is_dropped():
    async def chatty(codes, filters):
        return {"AA": Preview("A"), "ZZ": Preview("not asked")}

    register_type(LookupType("TASK", chatty))

    records = await engine.preview(["TASK@AA"], {})

    assert [(r.code, r.title) for r in records] == [("TASK@AA", "A")]


def test_a_repeated_registration_is_accepted_and_a_rival_is_refused():
    handler = Recorder({})
    register_type(LookupType("TASK", handler))
    register_type(LookupType("TASK", handler))

    with pytest.raises(ValueError, match="TASK@ is already registered"):
        register_type(LookupType("TASK", Recorder({})))
    register_type(LookupType("TASKGROUP", handler, aliases=("GROUP",)))
    with pytest.raises(ValueError, match="GROUP@ is already registered"):
        register_type(LookupType("OTHER", Recorder({}), aliases=("GROUP",)))
    assert type_for("OTHER") is None
