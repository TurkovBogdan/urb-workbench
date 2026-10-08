"""The ``notes`` module — documents with no owner, and the service the modules above build on.

**Level 1**: depends on the core and its infrastructure modules only, and refers to no application
module. The modules above use it: a task keeps its planning documents, a project its
documentation, a knowledge base its tree — each through a link table of its own, holding a
``note_code`` with ``ON DELETE CASCADE``. The module does not know who links to a note, and must
not: the use belongs to the user.

One table — ``notes``, without the module-name prefix: the module and the entity are one. The
schema is built by the ``ntm_*`` migrations on portable types — the chain runs on SQLite and
PostgreSQL.

The HTTP API lives in the ``internal`` zone under ``/notes`` (``api.py``) — the document page.
"""

from __future__ import annotations

from pathlib import Path
from typing import ClassVar

from fastapi import FastAPI

from src.core.config import Config
from src.core.module import Module
from src.modules.core_changes import ChangeEntity, Code, register_entity
from src.modules.notes import models
from src.modules.notes.api import router
from src.modules.notes.constants import NOTE_CODE_PREFIX

# A note has no refs: nothing it belongs to is known here. A screen listing documents recognises
# "this is about me" by the note codes it holds.
CHANGE_ENTITIES = (ChangeEntity("notes.note", models.Note, id=Code("code", NOTE_CODE_PREFIX)),)

_HERE = Path(__file__).resolve().parent


class NotesModule(Module):
    name: ClassVar[str] = "notes"
    description: ClassVar[str] = "Notes: markdown documents the modules above link to."
    migrations_dir = _HERE / "migrations" / "versions"
    internal_router = router
    internal_router_prefix = "/notes"

    def configure(self, app: FastAPI, config: Config) -> None:
        """Tell the change feed about notes, so an open document page follows edits from anywhere."""
        for entity in CHANGE_ENTITIES:
            register_entity(entity)


__all__ = ["CHANGE_ENTITIES", "NotesModule"]
