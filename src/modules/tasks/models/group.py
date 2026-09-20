"""ORM ``tasks_group`` — группа задач внутри пространства (биллинг, интерфейс, инфраструктура).

Группа отвечает на вопрос «про какую часть дела эта задача», а не «в каком она состоянии»: это
постоянная раскладка предметной области, а не колонка доски. Задача ссылается на группу
колонкой ``tasks.group_code`` (nullable → ``NULL`` = задача вне групп); группы по умолчанию
нет.

Слово взято то же, каким соседний модуль зовёт раскладку исследований (``research_group``):
понятие одно — корзина верхнеуровневых сущностей с названием, описанием и оформлением, — и
одинаковое имя избавляет агента от второго словаря. ``area`` не годилась ровно поэтому: в
ресёче зона это часть одного исследования, а не корзина поверх многих.

``sort`` задаёт порядок групп в интерфейсе: **больший sort = выше**. Второй ключ сортировки
обязателен, иначе группы с одинаковым ``sort`` (а по умолчанию он у всех один) меняются местами
между запросами.

FK на пространство — ``CASCADE``: группа вне пространства бессмысленна, физическое удаление
пространства уносит её с собой. Обычный путь удаления — логический (``deleted_at``).
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import ForeignKey, Index, Integer, String, text
from sqlalchemy.orm import Mapped, mapped_column

from src.core.database import SoftDeleteMixin
from src.core.database.runtime import Base
from src.core.database.types import timestamp
from src.core.utils.date import utc_now
from src.modules.tasks.constants import (
    CODE_LEN,
    COLOR_MAX,
    DESCRIPTION_MAX,
    ICON_MAX,
    SORT_DEFAULT,
    TITLE_MAX,
)


class TasksGroup(SoftDeleteMixin, Base):
    __tablename__ = "tasks_group"
    # Индекс на дочерней стороне FK: без него каждое удаление пространства читает таблицу групп
    # целиком, и список групп пространства — тоже full scan.
    __table_args__ = (Index("ix_tasks_group_workspace_code", "workspace_code"),)

    code: Mapped[str] = mapped_column(String(CODE_LEN), primary_key=True)
    workspace_code: Mapped[str] = mapped_column(
        String(CODE_LEN),
        ForeignKey(
            "workspaces.code",
            name="fk_tasks_group_workspace_code",
            ondelete="CASCADE",
        ),
    )
    title: Mapped[str] = mapped_column(String(TITLE_MAX))
    description: Mapped[str] = mapped_column(
        String(DESCRIPTION_MAX), default="", server_default=text("''")
    )
    color: Mapped[str] = mapped_column(
        String(COLOR_MAX), default="", server_default=text("''")
    )
    icon: Mapped[str] = mapped_column(
        String(ICON_MAX), default="", server_default=text("''")
    )
    sort: Mapped[int] = mapped_column(
        Integer, default=SORT_DEFAULT, server_default=text(str(SORT_DEFAULT))
    )
    created_at: Mapped[datetime] = mapped_column(timestamp(), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        timestamp(), default=utc_now, onupdate=utc_now
    )


__all__ = ["TasksGroup"]
