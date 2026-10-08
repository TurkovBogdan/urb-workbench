"""``tasks`` ORM models. Importing the package registers the tables in ``Base.metadata``.

The workspace is not here: it moved to the ``workspace`` module (level 1), and this module's
tables hold an FK to it via ``workspaces.code``. The target model must be in the metadata too —
where the schema is built from the models (``create_all`` in tests), the ``conftest`` next to
this package imports it, otherwise the FK has nothing to point at.

The ``notes`` table is the other FK target, and ``models/note.py`` imports its model itself: a
task note is not a task note without its document, so every schema built from these models has
both.
"""

from src.modules.tasks.models.group import TasksGroup
from src.modules.tasks.models.journal import TasksJournal
from src.modules.tasks.models.link import TasksLink
from src.modules.tasks.models.note import TasksNote
from src.modules.tasks.models.stage import TasksStage
from src.modules.tasks.models.task import TasksTask

__all__ = [
    "TasksGroup",
    "TasksTask",
    "TasksLink",
    "TasksStage",
    "TasksJournal",
    "TasksNote",
]
