"""ORM ``codex`` — a codex: a set of development rules on one theme, not tied to any project.

A codex is the root of its tree of notes (``codex_note``) and carries the rules of working in it
(``body``) — what ``codex_rules`` hands the agent. ``description`` is "when to turn to it": the
line by which the agent decides from the index whether this codex is needed at all.

``slug`` is the first segment of every path inside the codex (``python`` in ``python/test``). It
is unique among live codexes: two codexes with one slug could not be mounted into one workspace,
and a slug that is free in one workspace but taken in another would make mounting fail far from
the place the name was chosen. A soft-deleted codex frees its slug — hence the partial index.

Only the person edits a codex; the agent writes notes inside it.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Index, Integer, String, text
from sqlalchemy.orm import Mapped, mapped_column

from src.core.database import SoftDeleteMixin
from src.core.database.runtime import Base
from src.core.database.types import timestamp
from src.core.utils.date import utc_now
from src.modules.codex.constants import (
    BODY_MAX,
    CODE_LEN,
    DESCRIPTION_MAX,
    SLUG_MAX,
    SORT_DEFAULT,
    TITLE_MAX,
)

_LIVE = text("deleted_at IS NULL")


class Codex(SoftDeleteMixin, Base):
    __tablename__ = "codex"
    __table_args__ = (
        Index("ux_codex_slug", "slug", unique=True, sqlite_where=_LIVE, postgresql_where=_LIVE),
    )

    code: Mapped[str] = mapped_column(String(CODE_LEN), primary_key=True)
    slug: Mapped[str] = mapped_column(String(SLUG_MAX))
    title: Mapped[str] = mapped_column(String(TITLE_MAX))
    description: Mapped[str] = mapped_column(
        String(DESCRIPTION_MAX), default="", server_default=text("''")
    )
    body: Mapped[str] = mapped_column(String(BODY_MAX), default="", server_default=text("''"))
    sort: Mapped[int] = mapped_column(
        Integer, default=SORT_DEFAULT, server_default=text(str(SORT_DEFAULT))
    )
    created_at: Mapped[datetime] = mapped_column(timestamp(), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        timestamp(), default=utc_now, onupdate=utc_now
    )


__all__ = ["Codex"]
