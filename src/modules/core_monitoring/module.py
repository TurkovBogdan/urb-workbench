"""Module provider of the core_monitoring module.

An observability infra module: serves the jobs section (the list of registered scheduler jobs
+ their runs and logs). It has no tables/migrations/settings of its own — it reads the core
CRUD (`core/crud/tasks`, `tasks_logs`) and the scheduler registry.
"""

from __future__ import annotations

from typing import ClassVar

from fastapi import FastAPI

from src.core.config import Config
from src.core.loggers import get_logger
from src.core.loggers.logger_protocol import CoreLoggerProtocol
from src.core.module import Module
from src.modules.core_monitoring.api import internal_router
from src.modules.core_monitoring.constants import LOG_CHANNEL


class CoreMonitoringModule(Module):
    name: ClassVar[str] = "core_monitoring"
    description: ClassVar[str] = "Scheduler observability: the job list, their runs and logs."
    migrations_dir = None
    config_cls = None
    settings_schema = None
    internal_router = internal_router
    internal_router_prefix = ""

    @staticmethod
    def logger() -> CoreLoggerProtocol:
        return get_logger(LOG_CHANNEL)

    def configure(self, app: FastAPI, config: Config) -> None:
        pass


__all__ = ["CoreMonitoringModule"]
