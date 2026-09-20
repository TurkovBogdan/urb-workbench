"""ORM ``tasks`` — сама задача: единица работы человека или агента-исполнителя.

Таблица названа по модулю, без приставки: задача — его главная сущность, и ``tasks_task`` было бы
заиканием. Приставку несут спутники (``tasks_group``, ``tasks_link``, ``tasks_stage``,
``tasks_note``) — там она отвечает на вопрос «чьё это».

Строка описывает задачу целиком, **кроме её места в дереве**: родитель и позиция среди
соседей вынесены в ``tasks_link``. Причина — перенос ветки и перестановка соседей трогают только
таблицу связей, а карточка задачи (её текст, сроки, статус) при этом не переписывается; та же
развязка позволяет менять форму дерева, не трогая основную таблицу.

Поля-справочники — ``type`` (глубина ведения), ``status`` (где в работе), ``priority`` (насколько
срочно), ``created_by`` (кто завёл) — хранятся строками с именованными ``CHECK``, а не нативным
enum: ``CREATE TYPE`` не существует на SQLite, а миграции модуля катятся на обоих провайдерах.

Текст разложен по владельцу. Постановку пишет человек: ``description`` — цель, ``context`` —
детали и стартовые требования, ``constraints`` — что можно и чего нельзя, ``criteria`` —
требования к сдаче. ``body`` принадлежит агенту: у задачи это его план. Поэтому тело и стоит
последним в текстовом блоке, а не сразу за ``description``, как у остальных сущностей модуля.

Даты разделены по смыслу:

- ``deadline_at`` — крайний срок, ``timestamp``: единственная дата, которую задаче назначают;
- ``started_at`` / ``completed_at`` / ``canceled_at`` — отметки фаз, ставятся при смене статуса
  (``crud/task.py::task_update_status``) и больше не перебиваются: это факты, а не планы.

Индексы построены под три запроса, из которых состоит вся выдача: доска пространства по статусу,
раскладка по группам и план по срокам. Все три ведут с ``workspace_code`` — поперёк пространств
модуль не читает никогда.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import CheckConstraint, ForeignKey, Index, String, text
from sqlalchemy.orm import Mapped, mapped_column

from src.core.database import SoftDeleteMixin
from src.core.database.runtime import Base
from src.core.database.types import timestamp
from src.core.utils.date import utc_now
from src.modules.tasks.constants import (
    ACTOR_KINDS,
    BODY_MAX,
    CODE_LEN,
    CONSTRAINTS_MAX,
    CONTEXT_MAX,
    CRITERIA_MAX,
    DESCRIPTION_MAX,
    ENUM_VALUE_MAX,
    TASK_CREATED_BY_DEFAULT,
    TASK_PRIORITIES,
    TASK_PRIORITY_DEFAULT,
    TASK_STATUS_DEFAULT,
    TASK_STATUSES,
    TASK_TYPE_DEFAULT,
    TASK_TYPES,
    TITLE_MAX,
    sql_in,
)


class TasksTask(SoftDeleteMixin, Base):
    __tablename__ = "tasks"
    __table_args__ = (
        CheckConstraint(f"type IN ({sql_in(TASK_TYPES)})", name="ck_tasks_type"),
        CheckConstraint(f"status IN ({sql_in(TASK_STATUSES)})", name="ck_tasks_status"),
        CheckConstraint(
            f"priority IN ({sql_in(TASK_PRIORITIES)})", name="ck_tasks_priority"
        ),
        CheckConstraint(
            f"created_by IN ({sql_in(ACTOR_KINDS)})", name="ck_tasks_created_by"
        ),
        Index("ix_tasks_workspace_status", "workspace_code", "status"),
        Index("ix_tasks_workspace_group", "workspace_code", "group_code"),
        Index("ix_tasks_workspace_deadline", "workspace_code", "deadline_at"),
    )

    code: Mapped[str] = mapped_column(String(CODE_LEN), primary_key=True)
    workspace_code: Mapped[str] = mapped_column(
        String(CODE_LEN),
        ForeignKey(
            "workspaces.code",
            name="fk_tasks_workspace_code",
            ondelete="CASCADE",
        ),
    )
    # SET NULL, а не CASCADE: группу удаляют, когда меняют раскладку, — задачи при этом остаются
    # работой, просто перестают быть разложенными.
    group_code: Mapped[str | None] = mapped_column(
        String(CODE_LEN),
        ForeignKey(
            "tasks_group.code", name="fk_tasks_group_code", ondelete="SET NULL"
        ),
        nullable=True,
    )
    type: Mapped[str] = mapped_column(
        String(ENUM_VALUE_MAX),
        default=TASK_TYPE_DEFAULT,
        server_default=text(f"'{TASK_TYPE_DEFAULT}'"),
    )
    status: Mapped[str] = mapped_column(
        String(ENUM_VALUE_MAX),
        default=TASK_STATUS_DEFAULT,
        server_default=text(f"'{TASK_STATUS_DEFAULT}'"),
    )
    priority: Mapped[str] = mapped_column(
        String(ENUM_VALUE_MAX),
        default=TASK_PRIORITY_DEFAULT,
        server_default=text(f"'{TASK_PRIORITY_DEFAULT}'"),
    )
    title: Mapped[str] = mapped_column(String(TITLE_MAX))
    description: Mapped[str] = mapped_column(
        String(DESCRIPTION_MAX), default="", server_default=text("''")
    )
    context: Mapped[str] = mapped_column(
        String(CONTEXT_MAX), default="", server_default=text("''")
    )
    constraints: Mapped[str] = mapped_column(
        String(CONSTRAINTS_MAX), default="", server_default=text("''")
    )
    criteria: Mapped[str] = mapped_column(
        String(CRITERIA_MAX), default="", server_default=text("''")
    )
    body: Mapped[str] = mapped_column(
        String(BODY_MAX), default="", server_default=text("''")
    )
    deadline_at: Mapped[datetime | None] = mapped_column(timestamp(), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(timestamp(), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(timestamp(), nullable=True)
    canceled_at: Mapped[datetime | None] = mapped_column(timestamp(), nullable=True)
    created_by: Mapped[str] = mapped_column(
        String(ENUM_VALUE_MAX),
        default=TASK_CREATED_BY_DEFAULT,
        server_default=text(f"'{TASK_CREATED_BY_DEFAULT}'"),
    )
    created_at: Mapped[datetime] = mapped_column(timestamp(), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        timestamp(), default=utc_now, onupdate=utc_now
    )


__all__ = ["TasksTask"]
