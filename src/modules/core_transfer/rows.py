"""A table row ↔ a JSON object: one rule of translation for every table of every archive.

Keys are column names, values what survives JSON: a timestamp leaves in the API's own format
(``YYYY-MM-DD HH:MM:SS``, naive UTC), JSON columns stay objects, everything else is copied. There
is no description per table on purpose: the column list is in the model already, and a second copy
would drift from the first at the first migration.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, Integer, String

from src.core.utils.date import datetime_from_agent, datetime_to_agent
from src.modules.core_transfer.errors import ARCHIVE_INCONSISTENT, TransferError

_MISSING = object()

# SQLite keeps whatever it is given in any column, PostgreSQL refuses it mid-write: a value is
# checked against its column, or the two providers would part ways on a crafted archive.
_SCALARS: tuple[tuple[type, type], ...] = ((Boolean, bool), (Integer, int), (String, str))


def row_to_json(row: Any, *, omit: tuple[str, ...] = ()) -> dict[str, Any]:
    """An ORM row → an archive object, without the columns named."""
    values: dict[str, Any] = {}
    for column in row.__table__.columns:
        if column.name in omit:
            continue
        value = getattr(row, column.key)
        values[column.name] = datetime_to_agent(value) if isinstance(value, datetime) else value
    return values


def json_to_values(model: Any, data: dict[str, Any], *, omit: tuple[str, ...] = ()) -> dict[str, Any]:
    """An archive object → values for a row, by the model's columns.

    Unknown keys are ignored (the archive may come from a version with more columns); a missing
    column takes its default — but only a default there is: a column with neither a default nor a
    value means an archive not to be trusted.
    """
    values: dict[str, Any] = {}
    for column in model.__table__.columns:
        if column.name in omit:
            continue
        raw = data.get(column.name, _MISSING)
        values[column.key] = _fallback(model, column) if raw is _MISSING else _parse(model, column, raw)
    return values


def check_rows(model: Any, rows: list[dict[str, Any]], *, omit: tuple[str, ...] = ()) -> None:
    """Refuse at the plan what ``json_to_values`` would refuse at the write, files already taken."""
    for row in rows:
        json_to_values(model, row, omit=omit)


def moment(value: Any) -> datetime | None:
    """An archive timestamp as a datetime; ``None`` for an absent or malformed one."""
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime_from_agent(value)
    except ValueError:
        return None


def clip_to_columns(model: Any, values: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """Cut string values to their columns' width; return the values and the names cut.

    An archive from a version with a wider column would otherwise fail on PostgreSQL and be
    silently kept over the width on SQLite — the two providers must not diverge.
    """
    clipped: list[str] = []
    for column in model.__table__.columns:
        limit = getattr(column.type, "length", None)
        value = values.get(column.key)
        if limit is None or not isinstance(value, str) or len(value) <= limit:
            continue
        values[column.key] = value[:limit]
        clipped.append(column.name)
    return values, clipped


def _fallback(model: Any, column: Any) -> Any:
    if column.nullable:
        return None
    default = getattr(column.default, "arg", None)
    if default is not None and not callable(default):
        return default
    if default is not None and callable(default):
        # SQLAlchemy wraps a plain callable default into one that takes the execution context.
        return default(None)
    raise TransferError(
        ARCHIVE_INCONSISTENT,
        f"A row of {model.__tablename__} lacks the required field {column.name!r}",
        params={"detail": f"{model.__tablename__}.{column.name}"},
    )


def _parse(model: Any, column: Any, value: Any) -> Any:
    if value is None:
        if column.nullable:
            return None
        raise _not_of_column(model, column, value)
    if isinstance(column.type, DateTime):
        try:
            return datetime_from_agent(value)
        except (TypeError, ValueError) as error:
            raise TransferError(
                ARCHIVE_INCONSISTENT,
                f"The field {column.name!r} of {model.__tablename__} is not a timestamp: {value!r}",
                params={"detail": f"{model.__tablename__}.{column.name}"},
            ) from error
    for column_type, kind in _SCALARS:
        if isinstance(column.type, column_type):
            # ``True`` is an ``int`` to Python, not a position to a table.
            if not isinstance(value, kind) or (kind is int and isinstance(value, bool)):
                raise _not_of_column(model, column, value)
            break
    return value


def _not_of_column(model: Any, column: Any, value: Any) -> TransferError:
    return TransferError(
        ARCHIVE_INCONSISTENT,
        f"The field {column.name!r} of {model.__tablename__} does not fit its column: {value!r}",
        params={"detail": f"{model.__tablename__}.{column.name}"},
    )


__all__ = ["check_rows", "clip_to_columns", "json_to_values", "moment", "row_to_json"]
