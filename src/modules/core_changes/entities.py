"""What goes into the changes stream: entity declarations and their registry.

The stream knows no concrete entity. What to send into it is decided by the owning module: in
its ``configure()`` it declares the models whose changes the frontend sees — exactly the way
``tasks`` puts its counters into the ``workspace.stats`` registry. An undeclared model never
reaches the stream even when it changes: settings, logs and service tables do not leak out on
their own.

An entity name is a public contract: the frontend reads it (``web/src/features/<module>``
mirrors the backend module). Renaming ``tasks.task`` is like changing an API endpoint's
address, not an internal edit.

A declaration is checked right at registration: the code column and the ref columns must exist
on the model, and the name must be unique. Otherwise a renamed column would silently switch the
stream off, and the screen would stop updating without a single error.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import inspect


@dataclass(frozen=True)
class Code:
    """The column holding the code and the type prefix the code goes out with.

    In the database codes are bare (``3f1a…``), on the wire they are prefixed (``TASK@3f1a…``):
    the frontend compares against what it got from the endpoints, and the endpoints return the
    prefixed form. An empty prefix means the code as is.
    """

    column: str
    prefix: str = ""

    def render(self, value: object) -> str | None:
        if value is None or value == "":
            return None
        return f"{self.prefix}@{value}" if self.prefix else str(value)


@dataclass(frozen=True)
class ChangeEntity:
    """A stream entity: its name, model, what identifies it and what it refers to.

    ``refs`` are the codes of the entities this one belongs to: a stage's task, a task's group.
    They let a screen tell that a change is "about it" without knowing what a stage is. They are
    listed explicitly rather than derived from every foreign key: a ref no screen needs is noise.
    """

    name: str
    model: type
    id: Code
    refs: tuple[Code, ...] = ()


_BY_NAME: dict[str, ChangeEntity] = {}
_BY_MODEL: dict[type, ChangeEntity] = {}
_BY_TABLE: dict[str, ChangeEntity] = {}


def register_entity(entity: ChangeEntity) -> None:
    """Declare a stream entity. Repeating a declaration (app rebuild in tests) is not an error."""
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
    """Forget all declarations — for tests that rebuild the registry from scratch."""
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
