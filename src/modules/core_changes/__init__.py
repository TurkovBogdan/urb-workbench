"""core_changes — лента изменений данных: какие объявленные сущности созданы, изменены, удалены.

Модуль-владелец данных объявляет свои сущности (``register_entity``), массовые операции называют
тронутые коды (``mark_changes``); фронт слушает ``/internal/core/changes/stream``.
"""

from src.modules.core_changes.capture import CREATED, DELETED, UPDATED, mark_changes
from src.modules.core_changes.entities import ChangeEntity, Code, register_entity
from src.modules.core_changes.module import CoreChangesModule

__all__ = [
    "CREATED",
    "ChangeEntity",
    "Code",
    "CoreChangesModule",
    "DELETED",
    "UPDATED",
    "mark_changes",
    "register_entity",
]
