"""The core logger: writes to a file and to stdout."""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Any

_FMT = logging.Formatter(
    "%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)


class CoreLogger:
    """The core logger. Writes to a file; stdout is optional (turn it off for MCP servers)."""

    def __init__(
        self,
        logs_dir: Path,
        file_name: str = "core",
        level: int | str = logging.INFO,
        stdout: bool = True,
    ) -> None:
        # A `file_name` with a slash is treated as a path inside `logs_dir`:
        # "tasks/hh_vacancy" → logs_dir/tasks/hh_vacancy.log.
        log_path = logs_dir / f"{file_name}.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        logger_name = "core." + file_name.replace("/", ".")
        self._logger = logging.getLogger(logger_name)
        self._logger.setLevel(level)
        self._logger.propagate = False
        # Guard against re-initialisation (reload, tests): without it
        # `logging.getLogger` would return the same instance with handlers piled up.
        for h in list(self._logger.handlers):
            self._logger.removeHandler(h)
        file_handler = logging.FileHandler(log_path, encoding="utf-8")
        file_handler.setFormatter(_FMT)
        self._logger.addHandler(file_handler)
        if stdout:
            stream_handler = logging.StreamHandler(sys.stdout)
            stream_handler.setFormatter(_FMT)
            self._logger.addHandler(stream_handler)

    def set_level(self, level: int | str) -> None:
        self._logger.setLevel(level)

    def debug(self, msg: Any, *a: Any, **kw: Any) -> None: self._logger.debug(msg, *a, **kw)
    def info(self, msg: Any, *a: Any, **kw: Any) -> None: self._logger.info(msg, *a, **kw)
    def warning(self, msg: Any, *a: Any, **kw: Any) -> None: self._logger.warning(msg, *a, **kw)
    def error(self, msg: Any, *a: Any, **kw: Any) -> None: self._logger.error(msg, *a, **kw)
    def exception(self, msg: Any, *a: Any, **kw: Any) -> None: self._logger.exception(msg, *a, **kw)


__all__ = ["CoreLogger"]
