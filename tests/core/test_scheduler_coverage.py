"""Whether anything runs the scheduled tasks: a backend without a ticker, with no worker of this
installation alive next to it, leaves the cleanup and the reconciliations undone — and says so at
startup instead of letting the files pile up unnoticed."""

from __future__ import annotations

import os

import pytest

from src.core import process_registry
from src.core.config import Config
from src.core.scheduler.coverage import unattended_tasks, warn_if_unattended
from src.core.scheduler.registry import TaskRegistry

pytestmark = pytest.mark.pure


async def _noop(ctx) -> None:
    return None


def _registry(*, scheduled: bool = True, enabled: bool = True) -> TaskRegistry:
    registry = TaskRegistry()
    registry.register(
        module="core_storage",
        code="cleanup",
        name="File cleanup",
        description="",
        schedule="0 * * * *" if scheduled else None,
        handler=_noop,
        ttl=60,
        enabled=enabled,
    )
    return registry


def _record(role: str, *, app_env: str = "test", pid: int | None = None):
    return process_registry.ProcessRecord(
        pid=pid if pid is not None else os.getppid(),
        start_time=0.0,
        ppid=1,
        pgid=None,
        sid=None,
        role=role,
        hot_reload=False,
        port=None,
        app_env=app_env,
        checkout=str(process_registry.project_root()),
        argv=("src/app.py", "--worker"),
        written_at="",
    )


def _verified(monkeypatch: pytest.MonkeyPatch, *records) -> None:
    monkeypatch.setattr(process_registry, "read_records", lambda: list(records))
    monkeypatch.setattr(
        process_registry, "verify", lambda record: process_registry.RecordState.VERIFIED
    )


def test_a_backend_alone_leaves_the_scheduled_tasks_unattended(monkeypatch):
    _verified(monkeypatch)

    left = unattended_tasks(_registry(), ticking=False, app_env="test")

    assert [(entry.module, entry.code) for entry in left] == [("core_storage", "cleanup")]


def test_a_ticker_in_this_process_attends_them(monkeypatch):
    _verified(monkeypatch)

    assert unattended_tasks(_registry(), ticking=True, app_env="test") == []


@pytest.mark.parametrize("role", [process_registry.ROLE_WORKER, process_registry.ROLE_BACKEND_WORKER])
def test_a_live_worker_of_this_installation_attends_them(monkeypatch, role):
    _verified(monkeypatch, _record(role))

    assert unattended_tasks(_registry(), ticking=False, app_env="test") == []


def test_a_worker_of_another_profile_or_a_plain_backend_does_not(monkeypatch):
    """A worker of ``prod`` runs its own database's tasks, not this one's."""
    _verified(
        monkeypatch,
        _record(process_registry.ROLE_WORKER, app_env="prod"),
        _record(process_registry.ROLE_BACKEND),
    )

    assert len(unattended_tasks(_registry(), ticking=False, app_env="test")) == 1


def test_a_dead_worker_record_does_not_attend_them(monkeypatch):
    monkeypatch.setattr(process_registry, "read_records", lambda: [_record(process_registry.ROLE_WORKER)])
    monkeypatch.setattr(
        process_registry, "verify", lambda record: process_registry.RecordState.STALE
    )

    assert len(unattended_tasks(_registry(), ticking=False, app_env="test")) == 1


@pytest.mark.parametrize(("scheduled", "enabled"), [(False, True), (True, False)])
def test_a_task_on_request_only_or_switched_off_needs_no_worker(monkeypatch, scheduled, enabled):
    _verified(monkeypatch)

    assert unattended_tasks(_registry(scheduled=scheduled, enabled=enabled), ticking=False, app_env="test") == []


class _Recorder:
    def __init__(self) -> None:
        self.warnings: list[str] = []

    def warning(self, message: str, *args) -> None:
        self.warnings.append(message % args)


def test_the_warning_names_the_tasks_and_the_way_to_run_them(monkeypatch):
    from src.core.scheduler import coverage

    _verified(monkeypatch)
    log = _Recorder()
    monkeypatch.setattr(coverage, "_LOG", log)

    warn_if_unattended(Config(_env_file=None), registry=_registry(), ticking=False)

    [warning] = log.warnings
    assert "core_storage.cleanup" in warning
    assert "--worker" in warning and "MCP_STDIO_START_WORKER" in warning


def test_no_warning_when_a_worker_runs(monkeypatch):
    from src.core.scheduler import coverage

    _verified(monkeypatch, _record(process_registry.ROLE_WORKER))
    log = _Recorder()
    monkeypatch.setattr(coverage, "_LOG", log)

    warn_if_unattended(Config(_env_file=None), registry=_registry(), ticking=False)

    assert log.warnings == []


def test_the_stdio_shim_starts_the_worker_unless_told_otherwise(monkeypatch):
    """An installation whose ``.env`` predates the key gets the scheduler with its backend."""
    monkeypatch.delenv("MCP_STDIO_START_WORKER", raising=False)

    assert Config(_env_file=None).mcp_stdio_start_worker is True
