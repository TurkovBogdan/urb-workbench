"""``core_interface_settings`` — one row per setting that deviates from its default.

The module's only table. Keys, types and defaults are declared in ``registry.py``; only values
live here, and only those the human changed — a missing row means the default from the code.

There is no owner column: the application is designed for a single user with no accounts, and
an empty column would be a lie in the schema.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from src.core.database.runtime import Base
from src.core.database.types import json_value, timestamp
from src.modules.core_interface.constants import KEY_MAX_LENGTH


class InterfaceSetting(Base):
    __tablename__ = "core_interface_settings"

    key: Mapped[str] = mapped_column(String(KEY_MAX_LENGTH), primary_key=True)
    # ``NOT NULL`` on purpose: a reset to default deletes the row, so the table never has
    # two ways of saying "default".
    value: Mapped[Any] = mapped_column(json_value())
    created_at: Mapped[datetime] = mapped_column(timestamp())
    updated_at: Mapped[datetime] = mapped_column(timestamp())


__all__ = ["InterfaceSetting"]
