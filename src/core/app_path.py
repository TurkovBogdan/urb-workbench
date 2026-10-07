"""Runtime path resolver and typed application paths.

Works in two modes:

- **Dev** (running from source): the root is `<project>/runtime/<env>`,
  where `env` comes from `APP_ENV` (default `dev`).
- **Prod** (PyInstaller binary, `sys.frozen`): the root is the directory holding the
  executable. `logs/`, `cache/` etc. go next to the binary.

Use it through `AppPath.from_root()` — the low-level functions
(`resolve_runtime_root`, `project_root`) are only for rare cases.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path

# `src/core/app_path.py` → `<project>/`
_PROJECT_ROOT = Path(__file__).resolve().parents[2]


# ── Runtime root resolver ────────────────────────────────────────────────────

def resolve_runtime_root() -> Path:
    """Frozen → next to the binary; source → `<project>/runtime/<APP_ENV>` (default `dev`)."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent

    env = os.getenv("APP_ENV", "dev")
    return _PROJECT_ROOT / "runtime" / env


def project_root() -> Path:
    """The repository root (`<project>/`) — for committed artifacts such as the built
    frontend `web/dist`. This is NOT the runtime root (see resolve_runtime_root)."""
    return _PROJECT_ROOT


# ── Typed application paths ──────────────────────────────────────────────────

@dataclass(frozen=True)
class AppPath:
    """Canonical application paths; every field is absolute."""

    root: Path
    logs: Path
    cache: Path
    user: Path
    import_: Path
    tmp: Path
    storage_public: Path
    storage_protected: Path
    storage_private: Path

    @staticmethod
    def from_root(root: Path | None = None) -> "AppPath":
        """Build an `AppPath` from the given `root` or from the runtime root resolver."""
        r = Path(root).resolve() if root is not None else resolve_runtime_root()
        return AppPath(
            root=r,
            logs=r / "logs",
            cache=r / "cache",
            user=r / "user",
            import_=r / "import",
            tmp=r / "tmp",
            storage_public=r / "storage" / "public",
            storage_protected=r / "storage" / "protected",
            storage_private=r / "storage" / "private",
        )


def ensure_dirs(paths: AppPath) -> None:
    """Create every standard `AppPath` directory (idempotent)."""
    paths.root.mkdir(parents=True, exist_ok=True)
    paths.logs.mkdir(parents=True, exist_ok=True)
    paths.cache.mkdir(parents=True, exist_ok=True)
    paths.user.mkdir(parents=True, exist_ok=True)
    paths.import_.mkdir(parents=True, exist_ok=True)
    paths.tmp.mkdir(parents=True, exist_ok=True)
    paths.storage_public.mkdir(parents=True, exist_ok=True)
    paths.storage_protected.mkdir(parents=True, exist_ok=True)
    paths.storage_private.mkdir(parents=True, exist_ok=True)


__all__ = ["AppPath", "ensure_dirs", "project_root", "resolve_runtime_root"]
