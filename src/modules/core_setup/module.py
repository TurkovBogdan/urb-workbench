"""The ``core_setup`` module: a settings page that edits ``.env`` + restart.

The ENV/``Config`` layer (deploy-time), NOT runtime settings (``core_modules_settings``).
An ``.env`` edit takes effect by restarting the process. No DB/jobs — only an internal API.
"""

from __future__ import annotations

from typing import ClassVar

from src.core.module import Module
from src.modules.core_setup.api import router


class CoreSetupModule(Module):
    name: ClassVar[str] = "core_setup"
    description: ClassVar[str] = "Editing ENV/.env (deployment parameters) and restarting the process."
    internal_router = router
    internal_router_prefix = "/core/setup"
