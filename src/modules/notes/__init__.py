"""notes — markdown documents with no owner, and the service for the modules that use them.

A level 1 module: the modules above (tasks, a knowledge base) keep their own links to a note and
build on ``crud.note``.
"""

from src.modules.notes.module import NotesModule

__all__ = ["NotesModule"]
