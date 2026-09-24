"""Модуль ``core_changes`` — лента изменений данных для живого обновления фронта.

**Уровень 0**, инфраструктурный: стоит в списке раньше модулей, чьи сущности он разносит. Они
объявляют их в своём ``configure()`` (``register_entity``), а подписка на сессию ставится здесь же,
в ``configure()`` этого модуля, — до первого запроса и до первой записи.

Модуль не знает ни одной конкретной сущности: что уходит в поток, решает владелец данных (см.
``entities.py``). Своих таблиц нет — поток живёт в памяти процесса (``bus.py``).
"""

from __future__ import annotations

from typing import ClassVar

from fastapi import FastAPI

from src.core.config import Config
from src.core.module import Module
from src.modules.core_changes.api import router
from src.modules.core_changes.capture import install
from src.modules.core_changes.origin import OriginMiddleware


class CoreChangesModule(Module):
    name: ClassVar[str] = "core_changes"
    description: ClassVar[str] = (
        "Changes feed: tells the interface which declared entities were created, updated or "
        "deleted, so open screens refresh themselves."
    )
    internal_router = router
    internal_router_prefix = "/core/changes"

    def configure(self, app: FastAPI, config: Config) -> None:
        install()
        # Метка вкладки-источника (``X-Client-Id``) для каждого запроса — см. ``origin.py``.
        app.add_middleware(OriginMiddleware)


__all__ = ["CoreChangesModule"]
