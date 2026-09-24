"""Коды отказов HTTP-слоя пространства.

Их читает человек в интерфейсе: код ``workspace.<сущность>.<причина>`` интерфейс ищет в своём
словаре (``workspace.error.<сущность>.<причина>``), а текст ответа — английский запасной на случай,
если перевода нет. Модули уровнем выше (``tasks``) зовут те же коды, когда ищут пространство сами.
"""

from __future__ import annotations

WORKSPACE_NOT_FOUND = "workspace.workspace.not_found"
WORKSPACE_DELETED = "workspace.workspace.deleted"
WORKSPACE_NOT_DELETED = "workspace.workspace.not_deleted"

__all__ = ["WORKSPACE_DELETED", "WORKSPACE_NOT_DELETED", "WORKSPACE_NOT_FOUND"]
