"""Модуль ``tasks`` — хранилище задач одного разработчика и его агента-исполнителя.

**Уровень 2**: поверх ядра и поверх ``workspace``. Пространство здесь не своё — группа и задача
держат на него ``workspace_code``, и ни одна выборка не ходит поперёк пространств. Обратной
зависимости нет и быть не может: модуль уровнем ниже про задачи ничего не знает.

Пять таблиц: ``tasks_group`` → ``tasks`` (сама задача, названа по модулю — ``tasks_task`` было бы
заиканием), место задачи в дереве вынесено в ``tasks_link`` (ребро: родитель + позиция), а план
работы — в ``tasks_stage`` (этапы) и ``tasks_note`` (журнал). Схема строится миграциями ``tsm_*``
на портируемых типах — цепочка катится и на SQLite (dev), и на PostgreSQL. Начинается она с
``tsm_001_group``: таблицу пространства модуль не создаёт — она принадлежит ``workspace``, и
первая наша ревизия лишь объявляет на неё ``depends_on``, потому что цель FK обязана существовать
раньше ссылки.

Поверх слоя данных две поверхности. HTTP зоны ``internal`` (``api.py``, подпрефикс
``/workbench``) — её зовёт интерфейс, и она принимает пространство параметром. MCP-сервер
``workbench`` (``mcp/``) — его зовёт агент, и пространство он выбирает один раз на подключение,
после чего ни один инструмент его не принимает. Сервер собирает этот модуль, но тулы самого
пространства приходят из ``workspace/mcp/``: сервер один на стенд, а владение сущностью не
переезжает.

**Счётчики для карточки пространства регистрируются здесь.** Сколько в пространстве групп и задач —
знание этого модуля, а показать его должна страница пространств; поэтому мы кладём в реестр
``workspace.stats`` две считающие функции и ключи подписей, а модуль уровнем ниже собирает из
объявленного свою строку списка. Регистрация идёт в ``configure()`` — он зовётся один раз на
сборку приложения, до первого запроса, и повторная сборка (тесты) перезаписывает запись по ключу.

Подпрефикс задан явно, а не выведен из ``name``: имя модуля — Python-идентификатор с
подчёркиваниями, а сегмент URL по конвенции проекта пишется через дефис, и вывод одного из
другого сломался бы на первом же двусловном модуле.

**Почему ``/workbench``, а не ``/tasks``.** Ядровой модуль ``core_monitoring`` смонтирован без
префикса (``internal_router_prefix = ""``) и держит в корне зоны собственные ``/tasks`` и
``/tasks/{module}/{code}`` — расписание планировщика. С нашим подпрефиксом ``/tasks`` адрес
задачи (``/internal/tasks/tasks/{code}``) попадал в его маршрут с двумя сегментами и отвечал
``{"error": "task not registered"}``: деталка не работала вовсе. Ядро не наше, поэтому съехал
наш модуль. Переименован только внешний префикс HTTP — имя модуля, таблицы и коды прежние.
"""

from __future__ import annotations

from pathlib import Path
from typing import ClassVar

from fastapi import FastAPI

from src.core.config import Config
from src.core.module import Module
from src.modules.core_changes import ChangeEntity, Code, register_entity
from src.modules.tasks import models  # noqa: F401 — регистрирует модели в Base.metadata
from src.modules.tasks.api import router
from src.modules.tasks.mcp import mcp_server
from src.modules.tasks.crud import group as group_crud
from src.modules.tasks.crud import task as task_crud
from src.modules.tasks.constants import (
    GROUP_CODE_PREFIX,
    NOTE_CODE_PREFIX,
    STAGE_CODE_PREFIX,
    TASK_CODE_PREFIX,
)
from src.modules.workspace.constants import WORKSPACE_CODE_PREFIX
from src.modules.workspace.stats import WorkspaceCounter, register_counter

# Что из модуля видно ленте изменений (``core_changes``). Имена — публичный контракт с фронтом
# (``web/src/features/tasks``): переименование здесь — смена адреса, а не внутренняя правка.
# Ссылки — ровно те, по которым экран узнаёт «это про меня»: список — по пространству и группе,
# страница задачи — по своей задаче, у записи журнала — ещё и по этапу.
CHANGE_ENTITIES = (
    ChangeEntity(
        "tasks.task",
        models.TasksTask,
        id=Code("code", TASK_CODE_PREFIX),
        refs=(Code("workspace_code", WORKSPACE_CODE_PREFIX), Code("group_code", GROUP_CODE_PREFIX)),
    ),
    # Ребро дерева: место задачи среди соседей и её родитель. Кода своего у ребра нет — оно
    # названо задачей, чьё место описывает.
    ChangeEntity(
        "tasks.link",
        models.TasksLink,
        id=Code("task_code", TASK_CODE_PREFIX),
        refs=(Code("parent_code", TASK_CODE_PREFIX),),
    ),
    ChangeEntity(
        "tasks.group",
        models.TasksGroup,
        id=Code("code", GROUP_CODE_PREFIX),
        refs=(Code("workspace_code", WORKSPACE_CODE_PREFIX),),
    ),
    ChangeEntity(
        "tasks.stage",
        models.TasksStage,
        id=Code("code", STAGE_CODE_PREFIX),
        refs=(Code("task_code", TASK_CODE_PREFIX),),
    ),
    ChangeEntity(
        "tasks.note",
        models.TasksNote,
        id=Code("code", NOTE_CODE_PREFIX),
        refs=(Code("task_code", TASK_CODE_PREFIX), Code("stage_code", STAGE_CODE_PREFIX)),
    ),
)

_HERE = Path(__file__).resolve().parent


class TasksModule(Module):
    name: ClassVar[str] = "tasks"
    description: ClassVar[str] = (
        "Tasks: groups and a task tree with priorities and deadlines inside a workspace."
    )
    migrations_dir = _HERE / "migrations" / "versions"
    internal_router = router
    internal_router_prefix = "/workbench"
    # Значение — ФУНКЦИЯ, а не собранный сервер: словарь объявляется при импорте модуля, и
    # инстанс здесь затянул бы ``fastmcp`` в каждый процесс, включая воркер.
    # ``mcp_token_resolver`` мы намеренно НЕ ставим — почему, см. докстринг ``mcp/__init__``.
    mcp_servers = {"workbench": mcp_server}

    def configure(self, app: FastAPI, config: Config) -> None:
        """Объявить пространству, что мы в нём держим, — и чем это считать; ленте изменений — что
        из этого видно фронту (``CHANGE_ENTITIES``).

        Группы идут раньше задач (``sort``): в карточке сначала читается раскладка, потом её
        наполнение. Ключи подписей наши — переименование «группы» правится там же, где живёт
        сущность, а не в модуле, который про неё ничего не знает.
        """
        register_counter(
            WorkspaceCounter(
                key="groups",
                label_key="tasks.workspace.counter.groups",
                count_by_codes=group_crud.group_count_by_workspace_codes,
                sort=600,
            )
        )
        register_counter(
            WorkspaceCounter(
                key="tasks",
                label_key="tasks.workspace.counter.tasks",
                count_by_codes=task_crud.task_count_by_workspace_codes,
                sort=500,
            )
        )
        for entity in CHANGE_ENTITIES:
            register_entity(entity)


__all__ = ["TasksModule"]
