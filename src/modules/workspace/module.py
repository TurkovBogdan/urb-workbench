"""Модуль ``workspace`` — рабочее пространство как общий уровень изоляции данных.

**Уровень 1**: зависит только от ядра и его модулей, и ни на один прикладной модуль не
ссылается. Прикладные модули (уровень 2 и выше) зависят от него: ``tasks`` держит
``workspace_code`` у зоны и задачи, следующий модуль будет держать его у своих строк — и
каждый получает возможность сузить выборку до того пространства, в котором человек работает.

Одна таблица — ``workspaces``, без приставки имени модуля: модуль и сущность здесь одно и то же,
и ``workspace_workspace`` было бы заиканием. Схема строится миграциями ``wkm_*`` на портируемых
типах — цепочка катится и на SQLite (dev), и на PostgreSQL. Ревизий две, и разделены они не по
вкусу: таблица — цель кросс-модульного FK, а ``depends_on`` разрешено только на не-голову, так
что создающую ревизию обязана хоронить под собой следующая (``wkm_002`` с индексом списка).

Что лежит внутри пространства, модуль не знает и знать не должен. Счётчики содержимого для
карточки объявляют модули поверх — через ``stats.register_counter`` в своём ``configure()``.

HTTP-API живёт в зоне ``internal`` под подпрефиксом ``/workspace`` (``api.py``). Подпрефикс
задан явно, а не выведен из ``name``: имя модуля — Python-идентификатор с подчёркиваниями, а
сегмент URL по конвенции проекта пишется через дефис, и вывод одного из другого сломался бы на
первом же двусловном модуле.
"""

from __future__ import annotations

from pathlib import Path
from typing import ClassVar

from src.core.module import Module
from src.modules.workspace import models  # noqa: F401 — регистрирует модели в Base.metadata
from src.modules.workspace.api import router
from src.modules.workspace.mcp.auth import resolve_mcp_token

_HERE = Path(__file__).resolve().parent


class WorkspaceModule(Module):
    name: ClassVar[str] = "workspace"
    description: ClassVar[str] = (
        "Рабочие пространства: верхний уровень изоляции данных для модулей поверх."
    )
    migrations_dir = _HERE / "migrations" / "versions"
    internal_router = router
    internal_router_prefix = "/workspace"
    # Единственный на приложение резолвер MCP-токена. Живёт у модуля уровня 1 намеренно: он
    # ниже всех прикладных и переживёт любой из них — почему это важно, см. ``mcp/auth.py``.
    # ``staticmethod`` обязателен: доступ через экземпляр (``m.mcp_token_resolver``) связал бы
    # функцию как метод и подставил ``self`` первым аргументом.
    mcp_token_resolver = staticmethod(resolve_mcp_token)


__all__ = ["WorkspaceModule"]
