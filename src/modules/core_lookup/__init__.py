"""core_lookup — what an entity code stands for, for codes of any module, in one request.

The module that owns the codes registers a prefix and its ``preview`` handler
(``register_type``); the interface asks ``POST /internal/core/lookup/preview``.
"""

from src.modules.core_lookup.module import CoreLookupModule
from src.modules.core_lookup.registry import (
    WORKSPACE_FILTER,
    Filters,
    LookupType,
    Miss,
    Preview,
    PreviewResult,
    register_type,
)

__all__ = [
    "CoreLookupModule",
    "Filters",
    "LookupType",
    "Miss",
    "Preview",
    "PreviewResult",
    "WORKSPACE_FILTER",
    "register_type",
]
