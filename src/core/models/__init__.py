"""Core ORM models. Importing registers the tables in ``Base.metadata``.

``CoreLockRow`` lives together with ``CoreLock`` in ``src.core.locks`` —
it is imported here so the table still lands in the metadata.
"""

from src.core.locks import CoreLockRow  # noqa: F401
from src.core.models import module_settings  # noqa: F401
from src.core.models import module_state  # noqa: F401
from src.core.models import tasks  # noqa: F401

__all__ = ["module_settings", "module_state", "tasks"]
