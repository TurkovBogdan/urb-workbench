"""Registry of logging channels: name → ``CoreLoggerProtocol`` instance.

One logger per channel, created lazily by a factory. The default factory is
``CoreLogger`` with the file ``logs/<channel>.log``. The bootstrap (``apps/app/server.py``)
replaces the factory with the one it needs (level from settings, custom paths).
"""

from __future__ import annotations

from typing import Callable

from src.core.loggers.logger_protocol import CoreLoggerProtocol

LoggerFactory = Callable[[str], CoreLoggerProtocol]

DEFAULT_CHANNEL = "core"


def _default_factory(channel: str) -> CoreLoggerProtocol:
    """Lazy default: ``CoreLogger`` with the file ``logs/<channel>.log``.

    Exists so that early imports before ``set_factory`` don't crash and tests
    need no bootstrap. In a normal build the app bootstrap sets the factory.
    """
    from src.core.app_path import AppPath, ensure_dirs
    from src.core.loggers.core_logger import CoreLogger

    paths = AppPath.from_root()
    ensure_dirs(paths)
    return CoreLogger(logs_dir=paths.logs, file_name=channel)


class LoggerStore:
    """Class-based runtime store of loggers by channel."""

    _channels: dict[str, CoreLoggerProtocol] = {}
    _factory: LoggerFactory | None = None

    @classmethod
    def get(cls, channel: str = DEFAULT_CHANNEL) -> CoreLoggerProtocol:
        """Return the channel's logger. If absent, creates it through the factory."""
        if channel not in cls._channels:
            factory = cls._factory or _default_factory
            cls._channels[channel] = factory(channel)
        return cls._channels[channel]

    @classmethod
    def set(
        cls,
        logger: CoreLoggerProtocol | None,
        channel: str = DEFAULT_CHANNEL,
    ) -> None:
        """Pin the channel's logger. ``None`` — unpin; the next ``get`` recreates it."""
        if logger is None:
            cls._channels.pop(channel, None)
        else:
            cls._channels[channel] = logger

    @classmethod
    def set_factory(cls, factory: LoggerFactory | None) -> None:
        """Replace the factory. Every channel created lazily so far is dropped."""
        cls._factory = factory
        cls._channels.clear()

    @classmethod
    def reset(cls) -> None:
        """Full reset: the factory and every channel."""
        cls._channels.clear()
        cls._factory = None


def set_logger_factory(factory: LoggerFactory | None) -> None:
    """Replace the channel factory. Drops the instances already created."""
    LoggerStore.set_factory(factory)


__all__ = ["DEFAULT_CHANNEL", "LoggerFactory", "LoggerStore", "set_logger_factory"]
