"""Что попадает в поток изменений: объявления сущностей и их реестр.

Поток не знает ни одной конкретной сущности. Что в него слать, решает модуль-владелец: в своём
``configure()`` он объявляет модели, изменения которых видны фронту, — ровно тем же ходом, каким
``tasks`` кладёт счётчики в реестр ``workspace.stats``. Модель без объявления в поток не попадает,
даже если меняется: настройки, журналы и служебные таблицы наружу не уходят сами собой.

Имя сущности — публичный контракт: его читает фронт (``web/src/features/<модуль>`` зеркалит модуль
бэка). Переименовать ``tasks.task`` — всё равно что сменить адрес ручки API, а не внутренняя правка.

Объявление проверяется сразу при регистрации: колонка кода и колонки ссылок обязаны существовать
в модели, а имя — быть единственным. Переименованная колонка иначе молча выключила бы поток, и
экран перестал бы обновляться без единой ошибки.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import inspect


@dataclass(frozen=True)
class Code:
    """Колонка с кодом и тип-префикс, с которым код уходит наружу.

    В базе коды голые (``3f1a…``), на проводе — с префиксом (``TASK@3f1a…``): фронт сравнивает то,
    что получил от ручек, а ручки отдают префиксованную форму. Пустой префикс — код как есть.
    """

    column: str
    prefix: str = ""

    def render(self, value: object) -> str | None:
        if value is None or value == "":
            return None
        return f"{self.prefix}@{value}" if self.prefix else str(value)


@dataclass(frozen=True)
class ChangeEntity:
    """Сущность потока: её имя, модель, чем она названа и на кого ссылается.

    ``refs`` — коды сущностей, к которым эта относится: у этапа — его задача, у задачи — её группа.
    По ним экран понимает, что изменение «про него», не зная, что такое этап. Перечисляются явно, а
    не выводятся из всех внешних ключей: ссылка, которая никому на экране не нужна, — шум.
    """

    name: str
    model: type
    id: Code
    refs: tuple[Code, ...] = ()


_BY_NAME: dict[str, ChangeEntity] = {}
_BY_MODEL: dict[type, ChangeEntity] = {}
_BY_TABLE: dict[str, ChangeEntity] = {}


def register_entity(entity: ChangeEntity) -> None:
    """Объявить сущность потока. Повтор того же объявления (пересборка приложения в тестах) — не ошибка."""
    existing = _BY_NAME.get(entity.name)
    if existing is not None and existing != entity:
        raise ValueError(
            f"Change entity {entity.name!r} is already declared for {existing.model.__name__}"
        )
    columns = set(inspect(entity.model).columns.keys())
    for code in (entity.id, *entity.refs):
        if code.column not in columns:
            raise ValueError(
                f"Change entity {entity.name!r}: {entity.model.__name__} has no column "
                f"{code.column!r}"
            )
    _BY_NAME[entity.name] = entity
    _BY_MODEL[entity.model] = entity
    _BY_TABLE[entity.model.__table__.name] = entity


def entity_for_model(model: type) -> ChangeEntity | None:
    return _BY_MODEL.get(model)


def entity_for_table(table: str) -> ChangeEntity | None:
    return _BY_TABLE.get(table)


def entity_if_declared(name: str) -> ChangeEntity | None:
    return _BY_NAME.get(name)


def declared_entities() -> list[ChangeEntity]:
    return list(_BY_NAME.values())


def clear_entities() -> None:
    """Забыть все объявления — для тестов, которые собирают реестр заново."""
    _BY_NAME.clear()
    _BY_MODEL.clear()
    _BY_TABLE.clear()


__all__ = [
    "ChangeEntity",
    "Code",
    "clear_entities",
    "declared_entities",
    "entity_for_model",
    "entity_for_table",
    "entity_if_declared",
    "register_entity",
]
