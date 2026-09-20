"""ORM ``workspaces`` — рабочее пространство, верхний уровень изоляции данных.

Пространство не принадлежит никакому прикладному модулю: это ответ на вопрос «в чём я сейчас
работаю», и модули поверх (задачи сегодня, документация завтра) держат на него ссылку, чтобы
сузить свои выборки. Отдельный уровень нужен не для разделения доступа (пользователь один), а
чтобы «работа» и, скажем, «личное» не смешивались в одном списке.

Класс назван ``Workspace``, без приставки имени модуля (``TasksGroup`` и соседи её несут): сущность
здесь одна и совпадает с модулем, и ``WorkspaceWorkspace`` было бы повторением ради схемы
именования, а не ради ясности. Имя ТАБЛИЦЫ — ``workspaces``, тоже без приставки и по той же
причине: приставка отвечает на вопрос «чьё это» в модулях, где сущностей несколько
(``tasks_group``, ``tasks_task``), а здесь на него отвечает само имя, и ``workspace_workspace``
было бы тем же заиканием на уровне схемы.

Карточка минимальна: ``title``/``description`` (что это), ``icon``/``color`` — оформление
(``''`` = не выбрано, фронт рисует запасное). Ни иконка, ни цвет в БД не валидируются: рисовать
их умеет только фронт, а проверка на записи превратила бы расширение палитры в правку двух
файлов на двух языках.

PK — голый hex-код длиной ``CODE_LEN``; тип-префикс ``WORKSPACE@`` живёт на границе
(``workspace.codes``), в базе его нет. Удаление логическое (``deleted_at``).
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Index, String, text
from sqlalchemy.orm import Mapped, mapped_column

from src.core.database import SoftDeleteMixin
from src.core.database.runtime import Base
from src.core.database.types import timestamp
from src.core.utils.date import utc_now
from src.modules.workspace.constants import (
    CODE_LEN,
    COLOR_MAX,
    DESCRIPTION_MAX,
    ICON_MAX,
    TITLE_MAX,
)


class Workspace(SoftDeleteMixin, Base):
    __tablename__ = "workspaces"

    # Единственная выборка модуля — список: отсев удалённых, затем порядок по названию с кодом
    # как тайбрейком. Индекс повторяет её целиком, поэтому и колонки идут в этом порядке.
    __table_args__ = (Index("ix_workspaces_deleted_title", "deleted_at", "title", "code"),)

    code: Mapped[str] = mapped_column(String(CODE_LEN), primary_key=True)
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
    created_at: Mapped[datetime] = mapped_column(timestamp(), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        timestamp(), default=utc_now, onupdate=utc_now
    )


__all__ = ["Workspace"]
