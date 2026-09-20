"""Состав модулей приложения ``apps/app``.

Единый источник списка модулей: его переиспользуют сборка приложения
(``server.py``) и standalone-применение миграций (``app.py migrate``), чтобы
``version_locations`` совпадали с тем, что реально поднимает сервер.
"""

from __future__ import annotations

from src.core.module import Module
from src.modules.core_interface import CoreInterfaceModule
from src.modules.core_mcp import CoreMcpModule
from src.modules.core_monitoring import CoreMonitoringModule
from src.modules.core_setup import CoreSetupModule
from src.modules.tasks import TasksModule
from src.modules.workspace import WorkspaceModule


def build_modules() -> list[Module]:
    """Список модулей приложения в порядке регистрации.

    Поверх ядра (``src/core``: миграции, планировщик, зоны роутера, раздача SPA,
    settings-store) подключены ``core_setup`` — страница настроек ENV (правка ``.env``
    + рестарт), ``core_interface`` — настройки интерфейса пользователя (тема,
    гарнитуры, оформление документа и схем), ``core_monitoring`` — раздел задач (список +
    запуски + логи, только чтение), ``core_mcp`` — интроспекция модулей, поднятых как MCP-серверы
    (только чтение), ``workspace`` — рабочие пространства (общий уровень изоляции данных)
    и ``tasks`` — хранилище задач внутри пространства (группы, дерево задач, план и журнал).
    Новый модуль — добавить инстанс в список.

    **Порядок — это зависимости, а не вкус.** Модуль уровня 1 (``workspace``) стоит раньше тех,
    кто на него ссылается: ``configure()`` модулей поверх регистрирует в нём свои счётчики, а
    регистрировать в ещё не собранном модуле нечего. Между чужими ветками миграций порядок задаёт
    не этот список, а ``depends_on`` в самих ревизиях.
    """
    return [
        CoreSetupModule(),
        CoreInterfaceModule(),
        CoreMonitoringModule(),
        CoreMcpModule(),
        WorkspaceModule(),
        TasksModule(),
    ]


__all__ = ["build_modules"]
