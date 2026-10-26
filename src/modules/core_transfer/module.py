"""The ``core_transfer`` module — what every export and import of an entity has in common.

A platform module: like every ``core_*`` module it sits under the application levels and imports
only ``src/core`` and ``core_storage``. It knows no entity. A consumer (``tasks`` for a task,
``codex`` for a codex) describes its archive — the media type, the format name, the entries it
writes — and gets back the container that writes and reads it, the references rewritten by a map,
the shape of a conflict and the check of a person's decisions, the files taken into the storage
under the codes they had, and a place on disk for an upload between its requests.

No tables, no migrations, no routes: the routes are the consumer's, in its own zone, because what
an archive holds and who may import it are the consumer's questions.
"""

from __future__ import annotations

from typing import ClassVar

from src.core.module import Module


class CoreTransferModule(Module):
    name: ClassVar[str] = "core_transfer"
    version: ClassVar[str] = "1.0.0"
    description: ClassVar[str] = (
        "Moving an entity between installations: the archive container, references, conflicts "
        "of codes, files under their codes, uploads awaiting their import."
    )


__all__ = ["CoreTransferModule"]
