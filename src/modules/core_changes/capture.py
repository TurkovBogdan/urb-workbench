"""Collecting changes from the SQLAlchemy session and publishing them after commit.

The source is the session itself, not each CRUD separately: every write in the application goes
through it (``core/database/runtime.py::write_scope``), so a declared entity reaches the stream
however it was changed — from the interface, from an agent's MCP tool, or from a background job
in this process.

Three hooks:

- ``after_flush`` — ORM objects: ``new`` → ``created``, ``dirty`` with real changes →
  ``updated``, ``deleted`` → ``deleted``. Refs are taken from the current values, and for an
  updated row from the previous ones too: a task moved from one group to another concerns both;
- ``do_orm_execute`` — bulk ``update()`` / ``delete()``: they have no objects, only the table is
  known. The module passes the codes of such an operation explicitly (``mark_changes``); if it
  does not, an entity event with an empty ``ids`` goes out and the listener re-reads everything
  it holds. A forgotten mark costs an extra request, not a stale screen;
- ``after_commit`` — what was collected over the transaction goes out as one message. A rollback
  discards it: there is never an event about something that is not in the database.

A transaction's message is merged by the "entity + event" pair: a task touched three times is
one code. Created and then updated is only ``created``; created and deleted in the same
transaction never existed at all and is not reported.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass, field

from sqlalchemy import event, inspect
from sqlalchemy.orm import ORMExecuteState, Session

from src.modules.core_changes.bus import Message, bus
from src.modules.core_changes.entities import (
    ChangeEntity,
    entity_for_model,
    entity_for_table,
    entity_if_declared,
)
from src.modules.core_changes.origin import current_origin

CREATED = "created"
UPDATED = "updated"
DELETED = "deleted"
EVENTS = (CREATED, UPDATED, DELETED)

# The feed event name a transaction's message is sent under.
MESSAGE_EVENT = "changes"

_INFO_KEY = "core_changes.pending"


@dataclass
class _Group:
    ids: set[str] = field(default_factory=set)
    refs: set[str] = field(default_factory=set)


@dataclass
class _Pending:
    """What was collected over one session transaction."""

    groups: dict[tuple[str, str], _Group] = field(default_factory=dict)
    # Bulk operations for which codes may never arrive: (entity, event).
    bulk: set[tuple[str, str]] = field(default_factory=set)
    # What arrived as an explicit mark — the bulk-operation fallback is then not needed.
    marked: set[tuple[str, str]] = field(default_factory=set)
    # The tab that made the edit (``origin.py``); ``None`` — not a tab: the agent, a background job
    origin: str | None = None

    def add(self, name: str, event_name: str, ids: Iterable[str], refs: Iterable[str] = ()) -> None:
        group = self.groups.setdefault((name, event_name), _Group())
        group.ids.update(ids)
        group.refs.update(refs)

    def changes(self) -> list[dict[str, object]]:
        names = {name for name, _ in self.groups} | {name for name, _ in self.bulk}
        out: list[dict[str, object]] = []
        for name in sorted(names):
            created = set(self._group(name, CREATED).ids)
            deleted = set(self._group(name, DELETED).ids)
            # Born and died within one transaction — from the outside it never happened.
            ghosts = created & deleted
            ids = {
                CREATED: created - ghosts,
                UPDATED: self._group(name, UPDATED).ids - created - deleted,
                DELETED: deleted - ghosts,
            }
            for event_name in EVENTS:
                key = (name, event_name)
                group = self._group(name, event_name)
                unknown = key in self.bulk and key not in self.marked
                if ids[event_name]:
                    out.append(_item(name, event_name, ids[event_name], group.refs))
                elif unknown:
                    out.append(_item(name, event_name, (), group.refs))
        return out

    def _group(self, name: str, event_name: str) -> _Group:
        return self.groups.get((name, event_name)) or _Group()


def _item(name: str, event_name: str, ids: Iterable[str], refs: Iterable[str]) -> dict[str, object]:
    return {"entity": name, "event": event_name, "ids": sorted(ids), "refs": sorted(refs)}


def _pending(session: Session) -> _Pending:
    # The origin is read on the transaction's first write: the session lives inside one request,
    # and its context variable reaches here (SQLAlchemy async calls event handlers in a greenlet
    # that inherited the calling task's context — ``test_origin`` checks this).
    pending = session.info.get(_INFO_KEY)
    if pending is None:
        pending = session.info[_INFO_KEY] = _Pending(origin=current_origin.get())
    return pending


def _render_id(entity: ChangeEntity, obj: object) -> str | None:
    return entity.id.render(getattr(obj, entity.id.column))


def _refs(entity: ChangeEntity, obj: object, *, with_previous: bool) -> set[str]:
    out: set[str] = set()
    state = inspect(obj)
    for ref in entity.refs:
        values = [getattr(obj, ref.column)]
        if with_previous:
            values.extend(state.attrs[ref.column].history.deleted or ())
        for value in values:
            rendered = ref.render(value)
            if rendered is not None:
                out.add(rendered)
    return out


def _after_flush(session: Session, _flush_context: object) -> None:
    # Up to ``after_flush`` the new/dirty/deleted lists and the attribute history still describe
    # what was just flushed — later the session clears them.
    for event_name, objects, previous in (
        (CREATED, session.new, False),
        (UPDATED, session.dirty, True),
        (DELETED, session.deleted, False),
    ):
        for obj in objects:
            entity = entity_for_model(type(obj))
            if entity is None:
                continue
            if event_name == UPDATED and not session.is_modified(obj, include_collections=False):
                continue
            code = _render_id(entity, obj)
            if code is None:
                continue
            _pending(session).add(entity.name, event_name, [code], _refs(entity, obj, with_previous=previous))


def _do_orm_execute(state: ORMExecuteState) -> None:
    if not (state.is_update or state.is_delete):
        return
    table = getattr(state.statement, "table", None)
    entity = entity_for_table(getattr(table, "name", "")) if table is not None else None
    if entity is None:
        return
    _pending(state.session).bulk.add((entity.name, UPDATED if state.is_update else DELETED))


def _after_commit(session: Session) -> None:
    pending: _Pending | None = session.info.pop(_INFO_KEY, None)
    if pending is None:
        return
    changes = pending.changes()
    if changes:
        payload = {"origin": pending.origin, "changes": changes}
        bus.publish(Message(event=MESSAGE_EVENT, data=json.dumps(payload, ensure_ascii=False)))


def _after_rollback(session: Session) -> None:
    session.info.pop(_INFO_KEY, None)


def mark_changes(session: object, entity: str, event_name: str, codes: Iterable[str]) -> None:
    """Name the codes a bulk operation touched (``update()`` / ``delete()`` without objects).

    Called next to the operation itself, inside the same transaction: ``session`` is the session
    from ``write_scope``. Codes are bare, as in the database; the entity declaration adds the
    prefix.

    An undeclared entity is not an error but "not in the stream": the CRUD always calls the mark,
    while the entity is declared by the module's ``configure()``, which does not run at all in a
    bare CRUD run (the module's tests).
    """
    if event_name not in EVENTS:
        raise ValueError(f"Unknown change event {event_name!r}; expected one of {EVENTS}")
    declared = entity_if_declared(entity)
    if declared is None:
        return
    sync_session = getattr(session, "sync_session", session)
    rendered = [code for code in (declared.id.render(value) for value in codes) if code]
    pending = _pending(sync_session)
    pending.add(entity, event_name, rendered)
    pending.marked.add((entity, event_name))


_installed = False


def install() -> None:
    """Subscribe to the events of all sessions. A repeat call (app rebuild) does nothing."""
    global _installed
    if _installed:
        return
    event.listen(Session, "after_flush", _after_flush)
    event.listen(Session, "do_orm_execute", _do_orm_execute)
    event.listen(Session, "after_commit", _after_commit)
    event.listen(Session, "after_rollback", _after_rollback)
    _installed = True


__all__ = [
    "CREATED",
    "DELETED",
    "EVENTS",
    "MESSAGE_EVENT",
    "UPDATED",
    "install",
    "mark_changes",
]
