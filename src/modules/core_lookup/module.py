"""The ``core_lookup`` module — entities of any module, read by their codes in one request.

**Level 0**, infrastructure: it sits in the list before the modules that answer through it. They
register their code prefixes and handlers in their own ``configure()`` (``register_type``); the
module itself knows no entity and has no tables.
"""

from __future__ import annotations

from typing import ClassVar

from src.core.module import Module
from src.modules.core_lookup.api import router


class CoreLookupModule(Module):
    name: ClassVar[str] = "core_lookup"
    description: ClassVar[str] = (
        "Lookup: what an entity code stands for — its title, description and page — for codes "
        "of any module, in one request."
    )
    internal_router = router
    internal_router_prefix = "/core/lookup"


__all__ = ["CoreLookupModule"]
