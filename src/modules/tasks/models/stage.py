"""ORM ``tasks_stage`` — этап плана: единица работы внутри задачи.

Этапы заводятся у задач типа ``standard`` и тяжелее: ``simple`` — карточка без плана. Сам план
прозой лежит в ``tasks.body``, а здесь — конкретные шаги, каждый со своим состоянием и
доказательством.

Порядок держит ``number``, а не ``sort`` соседних таблиц: у этапа номер — часть его имени в
разговоре («третий заход на второй этап»), и растёт он вниз, от первого к последнему. Пара
``(task_code, number)`` уникальна — без этого два этапа с номером 3 появятся в первый же день, и
порядок станет неопределённым. Вставка в середину — передать номер явно и сдвинуть хвост.

``status`` берёт тот же справочник, что и задача, и отличается только умолчанием: этап заводят
уже назначенным (``planned``), потому что он часть плана, а не идея на будущее.

``evidence`` — указатель на доказательство выполнения: команда и её итог, путь к изменённому
файлу, сводка дифа. Переход в ``done`` с пустым ``evidence`` отказывает на записи (``crud``):
без этого шаг помечался бы сделанным без проверки, следующие рассуждали бы на ложной посылке, и
задача завершилась бы «успешно». ``finished_at`` ставит система при уходе в терминальный статус.

Логического удаления у этапа нет: плана без этапа не бывает, а выбранный и брошенный этап — это
``canceled``, а не скрытая строка.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import CheckConstraint, ForeignKey, Index, Integer, String, text
from sqlalchemy.orm import Mapped, mapped_column

from src.core.database.runtime import Base
from src.core.database.types import timestamp
from src.core.utils.date import utc_now
from src.modules.tasks.constants import (
    BODY_MAX,
    CODE_LEN,
    DESCRIPTION_MAX,
    ENUM_VALUE_MAX,
    EVIDENCE_MAX,
    STAGE_STATUS_DEFAULT,
    TASK_STATUSES,
    TITLE_MAX,
    sql_in,
)


class TasksStage(Base):
    __tablename__ = "tasks_stage"
    __table_args__ = (
        CheckConstraint(
            f"status IN ({sql_in(TASK_STATUSES)})", name="ck_tasks_stage_status"
        ),
        # Уникальность и порядок одним индексом: он же отдаёт этапы задачи уже отсортированными
        # и покрывает дочернюю сторону FK ``task_code``.
        Index("ix_tasks_stage_task_number", "task_code", "number", unique=True),
    )

    code: Mapped[str] = mapped_column(String(CODE_LEN), primary_key=True)
    task_code: Mapped[str] = mapped_column(
        String(CODE_LEN),
        ForeignKey(
            "tasks.code", name="fk_tasks_stage_task_code", ondelete="CASCADE"
        ),
    )
    number: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(
        String(ENUM_VALUE_MAX),
        default=STAGE_STATUS_DEFAULT,
        server_default=text(f"'{STAGE_STATUS_DEFAULT}'"),
    )
    title: Mapped[str] = mapped_column(String(TITLE_MAX))
    description: Mapped[str] = mapped_column(
        String(DESCRIPTION_MAX), default="", server_default=text("''")
    )
    body: Mapped[str] = mapped_column(
        String(BODY_MAX), default="", server_default=text("''")
    )
    evidence: Mapped[str] = mapped_column(
        String(EVIDENCE_MAX), default="", server_default=text("''")
    )
    started_at: Mapped[datetime | None] = mapped_column(timestamp(), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(timestamp(), nullable=True)
    created_at: Mapped[datetime] = mapped_column(timestamp(), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        timestamp(), default=utc_now, onupdate=utc_now
    )


__all__ = ["TasksStage"]
