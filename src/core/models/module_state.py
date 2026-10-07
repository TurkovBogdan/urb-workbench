"""ORM model of a ``core_modules_state`` row.

Arbitrary runtime state of a module (import cursors, counters, run markers).
A neighbour of ``core_modules_settings``, but for internal machine data rather
than user config: no schema, registry or UI. ``value`` is JSONB — the module
stores its structure directly.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from src.core.database.runtime import Base
from src.core.database.types import json_value, timestamp


class CoreModuleState(Base):
    __tablename__ = "core_modules_state"

    module: Mapped[str] = mapped_column(String(64), primary_key=True)
    code: Mapped[str] = mapped_column(String(128), primary_key=True)
    value: Mapped[Any] = mapped_column(json_value())
    created_at: Mapped[datetime] = mapped_column(timestamp())
    updated_at: Mapped[datetime] = mapped_column(timestamp())


__all__ = ["CoreModuleState"]
