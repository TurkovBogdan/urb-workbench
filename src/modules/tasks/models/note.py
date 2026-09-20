"""ORM ``tasks_note`` — журнал работы: решения, замечания, находки и факты одной таблицей.

Строка устроена как пара: **предмет** (``title`` + ``body``) и **разрешение** (``resolution``).
Предмет говорит, что поднято, разрешение — чем закрыто. Отсюда единственное состояние, которое
здесь есть: запись открыта, пока ``resolution`` пусто, и задача не сдаётся, пока открытые есть.
Отдельной колонки под это состояние нет — иначе агент проставил бы её сам, минуя условие.

``type`` решает, что описывает строка и кто пишет каждую её половину:

- ``decision`` — выбор по ходу работы; предмет пишет агент, разрешение — человек ответом или сам
  агент указателем на проверку. Решение с пустым разрешением и есть допущение, отдельного вида
  под него не заводится;
- ``remark`` — замечание постановщика; предмет пишет ТОЛЬКО человек (инструмента с этим типом у
  агента нет), разрешение — агент: как учёл;
- ``finding`` — находка вне задачи; поднимает агент, закрывает человек;
- ``fact`` — то, что нужно помнить дальше; закрыт в момент записи и в шлюзе не участвует.

``created_by`` здесь нет: автор выводится из типа. Таблица дописываемая — ни ``updated_at``, ни
отметки закрытия: отмена оформляется новой записью, а «когда именно закрыли» читателя не имеет.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import CheckConstraint, ForeignKey, Index, String, text
from sqlalchemy.orm import Mapped, mapped_column

from src.core.database.runtime import Base
from src.core.database.types import timestamp
from src.core.utils.date import utc_now
from src.modules.tasks.constants import (
    CODE_LEN,
    ENUM_VALUE_MAX,
    NOTE_BODY_MAX,
    NOTE_TYPES,
    RESOLUTION_MAX,
    TITLE_MAX,
    sql_in,
)


class TasksNote(Base):
    __tablename__ = "tasks_note"
    __table_args__ = (
        CheckConstraint(f"type IN ({sql_in(NOTE_TYPES)})", name="ck_tasks_note_type"),
        # Журнал читают целиком по задаче и в порядке появления — индекс повторяет этот запрос
        # и покрывает дочернюю сторону FK ``task_code``.
        Index("ix_tasks_note_task_created", "task_code", "created_at"),
        Index("ix_tasks_note_stage", "stage_code"),
    )

    code: Mapped[str] = mapped_column(String(CODE_LEN), primary_key=True)
    task_code: Mapped[str] = mapped_column(
        String(CODE_LEN),
        ForeignKey(
            "tasks.code", name="fk_tasks_note_task_code", ondelete="CASCADE"
        ),
    )
    # Запись о работе по этапу держит ссылку на него; запись про задачу целиком — ``NULL``.
    # CASCADE, а не SET NULL: этап сносится только вместе с задачей, и осиротевших записей
    # тут не бывает.
    stage_code: Mapped[str | None] = mapped_column(
        String(CODE_LEN),
        ForeignKey(
            "tasks_stage.code", name="fk_tasks_note_stage_code", ondelete="CASCADE"
        ),
        nullable=True,
    )
    type: Mapped[str] = mapped_column(String(ENUM_VALUE_MAX))
    title: Mapped[str] = mapped_column(String(TITLE_MAX))
    body: Mapped[str] = mapped_column(
        String(NOTE_BODY_MAX), default="", server_default=text("''")
    )
    resolution: Mapped[str] = mapped_column(
        String(RESOLUTION_MAX), default="", server_default=text("''")
    )
    created_at: Mapped[datetime] = mapped_column(timestamp(), default=utc_now)


__all__ = ["TasksNote"]
