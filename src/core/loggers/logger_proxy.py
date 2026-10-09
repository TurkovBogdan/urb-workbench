"""Proxy wrappers over ``LoggerStore``: a single channel and a tee (fan-out).

The proxies exist so that a module-level ``_LOG = get_logger(...)`` sees
factory replacements made later via ``set_logger_factory``: every log call
is resolved through ``LoggerStore`` to the current instance.
"""

from __future__ import annotations

from typing import Any

from src.core.loggers.logger_protocol import CoreLoggerProtocol
from src.core.loggers.logger_store import DEFAULT_CHANNEL, LoggerStore


class _LoggerProxy:
    """Proxy for a single channel."""

    def __init__(self, channel: str = DEFAULT_CHANNEL) -> None:
        self._channel = channel

    def set_level(self, level: int | str) -> None:
        LoggerStore.get(self._channel).set_level(level)

    def debug(self, msg: Any, *a: Any, **kw: Any) -> None:
        LoggerStore.get(self._channel).debug(msg, *a, **kw)

    def info(self, msg: Any, *a: Any, **kw: Any) -> None:
        LoggerStore.get(self._channel).info(msg, *a, **kw)

    def warning(self, msg: Any, *a: Any, **kw: Any) -> None:
        LoggerStore.get(self._channel).warning(msg, *a, **kw)

    def error(self, msg: Any, *a: Any, **kw: Any) -> None:
        LoggerStore.get(self._channel).error(msg, *a, **kw)

    def exception(self, msg: Any, *a: Any, **kw: Any) -> None:
        LoggerStore.get(self._channel).exception(msg, *a, **kw)


class _TeeProxy:
    """Fan-out proxy: every call is forwarded to all channels."""

    def __init__(self, channels: tuple[str, ...]) -> None:
        self._channels = channels

    def set_level(self, level: int | str) -> None:
        for ch in self._channels:
            LoggerStore.get(ch).set_level(level)

    def debug(self, msg: Any, *a: Any, **kw: Any) -> None:
        for ch in self._channels:
            LoggerStore.get(ch).debug(msg, *a, **kw)

    def info(self, msg: Any, *a: Any, **kw: Any) -> None:
        for ch in self._channels:
            LoggerStore.get(ch).info(msg, *a, **kw)

    def warning(self, msg: Any, *a: Any, **kw: Any) -> None:
        for ch in self._channels:
            LoggerStore.get(ch).warning(msg, *a, **kw)

    def error(self, msg: Any, *a: Any, **kw: Any) -> None:
        for ch in self._channels:
            LoggerStore.get(ch).error(msg, *a, **kw)

    def exception(self, msg: Any, *a: Any, **kw: Any) -> None:
        for ch in self._channels:
            LoggerStore.get(ch).exception(msg, *a, **kw)


def get_logger(*channels: str) -> CoreLoggerProtocol:
    """Proxy for one or several channels. With no arguments — the ``core`` channel."""
    if not channels:
        return _LoggerProxy(DEFAULT_CHANNEL)
    if len(channels) == 1:
        return _LoggerProxy(channels[0])
    return _TeeProxy(channels)


__all__ = ["_LoggerProxy", "_TeeProxy", "get_logger"]
