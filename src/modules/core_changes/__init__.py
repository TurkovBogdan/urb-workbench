"""core_changes — the data changes feed: which declared entities were created, updated, deleted.

The module that owns the data declares its entities (``register_entity``), bulk operations name
the codes they touched (``mark_changes``); the frontend listens on the WebSocket
``/internal/core/changes/ws``.
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
