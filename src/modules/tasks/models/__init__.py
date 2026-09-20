"""ORM-модели ``tasks``. Импорт пакета регистрирует таблицы в ``Base.metadata``.

Пространство сюда не входит: оно переехало в модуль ``workspace`` (уровень 1), и таблицы модуля
держат на него FK через ``workspaces.code``. Модель-цель нужна и в метаданных — там,
где схема строится из моделей (``create_all`` в тестах), её импортирует ``conftest`` рядом
с этим пакетом, иначе FK некуда указывать.
"""

from src.modules.tasks.models.group import TasksGroup
from src.modules.tasks.models.link import TasksLink
from src.modules.tasks.models.note import TasksNote
from src.modules.tasks.models.stage import TasksStage
from src.modules.tasks.models.task import TasksTask

__all__ = [
    "TasksGroup",
    "TasksTask",
    "TasksLink",
    "TasksStage",
    "TasksNote",
]
