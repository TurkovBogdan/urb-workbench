"""ORM ``tasks_link`` — ребро дерева задач: где задача стоит и под кем.

Ровно одна строка на задачу (``task_code`` — и PK, и FK), поэтому «место в дереве» у задачи
единственно по конструкции, а не по договорённости: второй родитель здесь физически не
помещается. Без строки связи задача дереву не принадлежит вовсе — поэтому ``task_create``
заводит её в той же транзакции, что и саму задачу.

- ``parent_code`` ``NULL`` — корень пространства (а не «родитель потерялся»): корней у
  пространства много, и отдельного признака им не нужно.
- ``sort`` — позиция среди соседей, **больший sort = выше**; шаг ``SORT_STEP`` оставляет место
  для вставок между соседями без перенумерации списка.

Дети родителя идут одним полотном: заголовков кучек внутри связи здесь нет, весь порядок несёт
``sort``.

``created_at`` тут нет намеренно: время появления ребра — это время появления задачи, а
дублировать его значит завести второй источник правды. ``updated_at`` есть — он отвечает на
другой вопрос: когда ветку последний раз двигали.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import ForeignKey, Index, Integer, String, text
from sqlalchemy.orm import Mapped, mapped_column

from src.core.database.runtime import Base
from src.core.database.types import timestamp
from src.core.utils.date import utc_now
from src.modules.tasks.constants import CODE_LEN, SORT_DEFAULT


class TasksLink(Base):
    __tablename__ = "tasks_link"
    # Главный запрос дерева — «дети такого-то по порядку»; индекс отдаёт их уже отсортированными
    # и заодно покрывает дочернюю сторону FK ``parent_code``.
    __table_args__ = (Index("ix_tasks_link_parent_sort", "parent_code", "sort"),)

    task_code: Mapped[str] = mapped_column(
        String(CODE_LEN),
        ForeignKey(
            "tasks.code", name="fk_tasks_link_task_code", ondelete="CASCADE"
        ),
        primary_key=True,
    )
    parent_code: Mapped[str | None] = mapped_column(
        String(CODE_LEN),
        ForeignKey(
            "tasks.code", name="fk_tasks_link_parent_code", ondelete="CASCADE"
        ),
        nullable=True,
    )
    sort: Mapped[int] = mapped_column(
        Integer, default=SORT_DEFAULT, server_default=text(str(SORT_DEFAULT))
    )
    updated_at: Mapped[datetime] = mapped_column(
        timestamp(), default=utc_now, onupdate=utc_now
    )


__all__ = ["TasksLink"]
