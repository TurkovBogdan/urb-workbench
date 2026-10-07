"""Global log: tees all of stdout/stderr into logs/global.log.

Call it as early as possible at process start — before any other initialisation.
Works for the GUI, MCP servers and any other entry point of the platform.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import TextIO

from src.core.app_path import resolve_runtime_root


class _TeeStream:
    def __init__(self, original: TextIO, log_file: Path) -> None:
        self._original = original
        self._file     = log_file.open("a", encoding="utf-8", buffering=1)

    def write(self, text: str) -> int:
        # the file goes first, so an exception in the original stream cannot block the write
        self._file.write(text)
        if self._original is not None:
            try:
                self._original.write(text)
                self._original.flush()
            except Exception:
                pass
        return len(text)

    def flush(self) -> None:
        self._file.flush()
        if self._original is not None:
            try:
                self._original.flush()
            except Exception:
                pass

    def fileno(self) -> int:
        if self._original is not None:
            return self._original.fileno()
        raise OSError("stream has no fileno")

    def isatty(self) -> bool:
        return False


def install() -> None:
    """Redirect stdout and stderr: write to the original + logs/global.log."""
    logs_dir = resolve_runtime_root() / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    log_file = logs_dir / "app.log"

    # capture sys.stdout/stderr as they are right now (an IDE may have replaced them already)
    sys.stdout = _TeeStream(sys.stdout, log_file)  # type: ignore[assignment]
    sys.stderr = _TeeStream(sys.stderr, log_file)  # type: ignore[assignment]


__all__ = ["install"]
