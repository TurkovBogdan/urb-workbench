"""Сбор изменений из сессии SQLAlchemy и их публикация после коммита.

Источник — сама сессия, а не каждый CRUD по отдельности: все записи приложения идут через неё
(``core/database/runtime.py::write_scope``), и объявленная сущность попадает в поток, как бы её ни
меняли — из интерфейса, из MCP-инструмента агента или из фоновой задачи этого процесса.

Три хода:

- ``after_flush`` — ORM-объекты: ``new`` → ``created``, ``dirty`` с настоящими изменениями →
  ``updated``, ``deleted`` → ``deleted``. Ссылки берутся из текущих значений, а у изменённой строки
  — ещё и из прежних: задача, переехавшая из группы в группу, касается обеих;
- ``do_orm_execute`` — массовые ``update()`` / ``delete()``: объектов у них нет, известна только
  таблица. Коды такой операции модуль передаёт явно (``mark_changes``); не передал — уходит событие
  сущности с пустым ``ids``, и слушатель перечитывает всё своё. Забытая пометка стоит лишнего
  запроса, а не устаревшего экрана;
- ``after_commit`` — собранное за транзакцию уходит одним сообщением. Откат выбрасывает его:
  события о том, чего в базе нет, не бывает.

Сообщение транзакции склеено по паре «сущность + событие»: задача, тронутая трижды, — один код.
Созданное и тут же изменённое — только ``created``; созданное и удалённое в той же транзакции не
существовало вовсе и не сообщается.
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

# Имя SSE-события, которым уходит сообщение транзакции.
MESSAGE_EVENT = "changes"

_INFO_KEY = "core_changes.pending"


@dataclass
class _Group:
    ids: set[str] = field(default_factory=set)
    refs: set[str] = field(default_factory=set)


@dataclass
class _Pending:
    """Собранное за одну транзакцию сессии."""

    groups: dict[tuple[str, str], _Group] = field(default_factory=dict)
    # Массовые операции, для которых кодов может не прийти: (сущность, событие).
    bulk: set[tuple[str, str]] = field(default_factory=set)
    # Что пришло явной пометкой — страховка массовой операции тогда не нужна.
    marked: set[tuple[str, str]] = field(default_factory=set)
    # Вкладка, сделавшая правку (``origin.py``); ``None`` — не вкладка: агент, фоновая задача.
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
            # Родилось и умерло в одной транзакции — снаружи этого не было.
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
    # Источник читается при первой записи транзакции: сессия живёт внутри одного запроса, и его
    # переменная контекста доходит сюда (обработчики событий SQLAlchemy async зовёт в greenlet,
    # унаследовавшем контекст вызвавшей задачи — это проверяет ``test_origin``).
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
    # До ``after_flush`` списки new/dirty/deleted и история атрибутов ещё описывают только что
    # сброшенное — позже сессия их очистит.
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
    """Назвать коды, которые тронула массовая операция (``update()`` / ``delete()`` без объектов).

    Зовётся рядом с самой операцией, внутри той же транзакции: ``session`` — сессия из
    ``write_scope``. Коды голые, как в базе; префикс ставит объявление сущности.

    Необъявленная сущность — не ошибка, а «не в потоке»: CRUD зовёт пометку всегда, а объявляет
    сущность ``configure()`` модуля, которого в голом прогоне CRUD (тесты модуля) нет вовсе.
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
    """Подписаться на события всех сессий. Повторный вызов (пересборка приложения) ничего не делает."""
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
