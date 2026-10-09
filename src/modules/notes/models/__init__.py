"""ORM models of ``notes``. Importing the package registers the table in ``Base.metadata``."""

from src.modules.notes.models.note import Note

__all__ = ["Note"]
