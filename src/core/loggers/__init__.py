"""The core logger: channels on top of ``LoggerStore``.

Usage::

    from src.core.loggers import get_logger

    _LOG = get_logger("tasks")          # logs/tasks.log
    _LOG = get_logger()                 # the "core" channel
    _LOG = get_logger("hh.browser", "tasks")  # fan-out to both channels
"""

from __future__ import annotations

from src.core.loggers.logger_proxy import get_logger
from src.core.loggers.logger_store import LoggerStore, set_logger_factory

__all__ = ["LoggerStore", "get_logger", "set_logger_factory"]
