"""core_setup — a settings page that edits ``.env`` and restarts the server.

Edits the ENV/``Config`` layer (deploy-time: DB provider, connection, ports, worker); changes
take effect by restarting the process (``os.execv``). Separate from the runtime settings
(``core/settings`` → ``/core/settings``), which apply hot.
"""

from src.modules.core_setup.module import CoreSetupModule

__all__ = ["CoreSetupModule"]
