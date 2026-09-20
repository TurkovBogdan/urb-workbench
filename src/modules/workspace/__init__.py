"""workspace — рабочее пространство как общий уровень изоляции данных (модуль уровня 1).

Держит одну сущность и точку расширения к ней: модули поверх ссылаются на пространство своим
``workspace_code`` и объявляют счётчики содержимого для его карточки (``stats``).
"""

from src.modules.workspace.module import WorkspaceModule

__all__ = ["WorkspaceModule"]
