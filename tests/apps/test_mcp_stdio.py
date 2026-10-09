"""apps/app.mcp_stdio: the shim — code resolution, backend detect/spawn, browser, proxy.

Launching the backend itself and polling for readiness live in `src/core/backend_launch.py`
(shared with the updater) — their tests sit alongside, `tests/core/test_backend_launch.py`.
"""

from __future__ import annotations

import subprocess
import types
from datetime import datetime

import pytest

from src.apps.app import mcp_stdio
from src.core import backend_launch
from src.core.backend_launch import BackendHealth
from src.core.maintenance import MaintenanceFlag


def _cfg(**over):
    base = dict(
        server_host="127.0.0.1", server_port=12200, app_log_level="INFO",
        mcp_token="", mcp_stdio_code="", mcp_stdio_start_worker=False,
        mcp_stdio_boot_timeout=30, mcp_stdio_open_browser=True, mcp_workspace="",
    )
    return types.SimpleNamespace(**{**base, **over})


@pytest.fixture(autouse=True)
def no_maintenance_flag(monkeypatch):
    """The shim reads the flag on the live machine — tests must not depend on whether an update
    is running there; the test of the gate itself overrides this with its own value."""
    monkeypatch.setattr(mcp_stdio.maintenance, "active", lambda: None)


@pytest.mark.pure
def test_resolve_code_prefers_config():
    assert mcp_stdio._resolve_code(_cfg(mcp_stdio_code="explicit")) == "explicit"


@pytest.mark.pure
def test_resolve_code_picks_sole_mounted_server(monkeypatch):
    """Empty → the only server the modules mount.

    The module list is monkeypatched rather than taken live: the build already has two servers,
    and a test of the "only one, so that one" rule must not break every time a third is added.
    """
    monkeypatch.setattr(
        "src.apps.app.modules.build_modules",
        lambda: [types.SimpleNamespace(mcp_servers={"only": object()})],
    )
    assert mcp_stdio._resolve_code(_cfg()) == "only"


@pytest.mark.pure
def test_resolve_code_refuses_loudly_when_several_are_mounted(monkeypatch):
    """Several servers — silently picking one is not allowed, and the refusal names the setting.

    The module list is set right here, as in the single-server test: the build currently has one
    server, and the several-servers rule must not be testable only in the periods when there
    happen to be more than one.

    This is also an update trap: a config copied back when there was a single server carries no
    pin and stops connecting once a second one appears. The error has to say how to fix it —
    otherwise "Connection Failed" explains nothing.
    """
    monkeypatch.setattr(
        "src.apps.app.modules.build_modules",
        lambda: [
            types.SimpleNamespace(mcp_servers={"first": object()}),
            types.SimpleNamespace(mcp_servers={"second": object()}),
        ],
    )
    with pytest.raises(RuntimeError, match="MCP_STDIO_CODE"):
        mcp_stdio._resolve_code(_cfg())


@pytest.mark.pure
def test_proxy_introduces_the_connection_with_a_session_header():
    """The shim introduces itself to the backend: without this header agent sessions are
    indistinguishable."""
    from src.core.mcp_headers import MCP_SESSION_HEADER, MCP_WORKSPACE_HEADER

    headers = mcp_stdio._session_headers(_cfg())

    assert headers[MCP_SESSION_HEADER]
    # No workspace in the config — so no default header either: the backend would read an empty
    # value as "configured as empty", which is a different state.
    assert MCP_WORKSPACE_HEADER not in headers


@pytest.mark.pure
def test_each_connection_gets_its_own_session_id():
    """A key per process, not per installation: two clients — two independent sessions."""
    first = mcp_stdio._session_headers(_cfg())
    second = mcp_stdio._session_headers(_cfg())

    from src.core.mcp_headers import MCP_SESSION_HEADER

    assert first[MCP_SESSION_HEADER] != second[MCP_SESSION_HEADER]


@pytest.mark.pure
def test_configured_workspace_rides_along():
    from src.core.mcp_headers import MCP_WORKSPACE_HEADER

    headers = mcp_stdio._session_headers(_cfg(mcp_workspace="WORKSPACE@18e948522f"))

    assert headers[MCP_WORKSPACE_HEADER] == "WORKSPACE@18e948522f"


@pytest.mark.pure
def test_spawn_backend_command_env_and_detached(monkeypatch, tmp_path):
    rec = {}

    def _fake_popen(cmd, **kw):
        rec["cmd"] = cmd
        rec["kw"] = kw

    monkeypatch.setattr(backend_launch.subprocess, "Popen", _fake_popen)
    monkeypatch.setattr(mcp_stdio, "_backend_log_path", lambda c: tmp_path / "backend.log")

    mcp_stdio._spawn_backend(_cfg(mcp_stdio_start_worker=False))

    assert rec["cmd"][1].endswith("/app.py")
    assert "--backend" in rec["cmd"]
    assert "--worker" not in rec["cmd"]
    assert rec["kw"]["env"]["SERVER_ENABLED"] == "true"
    assert rec["kw"]["env"]["WORKER_ENABLED"] == "false"
    assert rec["kw"]["env"]["SERVER_HOT_RELOAD"] == "false"
    assert rec["kw"]["start_new_session"] is True
    assert rec["kw"]["stdin"] is subprocess.DEVNULL


@pytest.mark.pure
def test_spawn_backend_adds_worker_when_enabled(monkeypatch, tmp_path):
    rec = {}
    monkeypatch.setattr(
        backend_launch.subprocess, "Popen", lambda cmd, **kw: rec.update(cmd=cmd, kw=kw)
    )
    monkeypatch.setattr(mcp_stdio, "_backend_log_path", lambda c: tmp_path / "backend.log")

    mcp_stdio._spawn_backend(_cfg(mcp_stdio_start_worker=True))

    assert "--worker" in rec["cmd"]
    assert rec["kw"]["env"]["WORKER_ENABLED"] == "true"


@pytest.mark.pure
def test_ensure_backend_noop_when_alive(monkeypatch):
    calls = []
    monkeypatch.setattr(mcp_stdio, "probe_health", lambda c: BackendHealth("ok"))
    monkeypatch.setattr(mcp_stdio, "_spawn_backend", lambda c: calls.append("spawn"))
    monkeypatch.setattr(mcp_stdio, "_open_home", lambda c: calls.append("browser"))
    mcp_stdio._ensure_backend(_cfg())
    assert calls == []


@pytest.mark.pure
def test_ensure_backend_boots_then_opens_browser(monkeypatch):
    calls = []
    monkeypatch.setattr(mcp_stdio, "probe_health", lambda c: None)
    monkeypatch.setattr(mcp_stdio, "_spawn_backend", lambda c: calls.append("spawn"))
    monkeypatch.setattr(mcp_stdio, "wait_until_ready", lambda c, timeout: BackendHealth("ok"))
    monkeypatch.setattr(mcp_stdio, "_open_home", lambda c: calls.append("browser"))
    mcp_stdio._ensure_backend(_cfg())
    assert calls == ["spawn", "browser"]


@pytest.mark.pure
def test_ensure_backend_raises_and_skips_browser_on_timeout(monkeypatch):
    calls = []
    monkeypatch.setattr(mcp_stdio, "probe_health", lambda c: None)
    monkeypatch.setattr(mcp_stdio, "_spawn_backend", lambda c: calls.append("spawn"))
    monkeypatch.setattr(mcp_stdio, "wait_until_ready", lambda c, timeout: None)
    monkeypatch.setattr(mcp_stdio, "_open_home", lambda c: calls.append("browser"))
    with pytest.raises(RuntimeError):
        mcp_stdio._ensure_backend(_cfg())
    assert calls == ["spawn"]


@pytest.mark.pure
def test_ensure_backend_raises_when_the_spawned_backend_comes_up_degraded(monkeypatch):
    """It came up but the schema is behind: no browser, and the revisions are named."""
    calls = []
    monkeypatch.setattr(mcp_stdio, "probe_health", lambda c: None)
    monkeypatch.setattr(mcp_stdio, "_spawn_backend", lambda c: calls.append("spawn"))
    monkeypatch.setattr(
        mcp_stdio, "wait_until_ready", lambda c, timeout: BackendHealth("degraded", ("rem_005",))
    )
    monkeypatch.setattr(mcp_stdio, "_open_home", lambda c: calls.append("browser"))

    with pytest.raises(RuntimeError) as refusal:
        mcp_stdio._ensure_backend(_cfg())

    assert "rem_005" in str(refusal.value)
    assert calls == ["spawn"]


@pytest.mark.pure
def test_ensure_backend_fails_fast_on_degraded_backend(monkeypatch):
    """A degraded backend is alive — don't spawn a second one, name the cause and revisions."""
    calls = []
    degraded = BackendHealth("degraded", ("rem_005",))
    monkeypatch.setattr(mcp_stdio, "probe_health", lambda c: degraded)
    monkeypatch.setattr(mcp_stdio, "_spawn_backend", lambda c: calls.append("spawn"))
    monkeypatch.setattr(mcp_stdio, "wait_until_ready", lambda c, timeout: calls.append("wait"))
    monkeypatch.setattr(mcp_stdio, "_open_home", lambda c: calls.append("browser"))

    with pytest.raises(RuntimeError) as refusal:
        mcp_stdio._ensure_backend(_cfg())

    assert "degraded" in str(refusal.value)
    assert "rem_005" in str(refusal.value)
    assert calls == []


@pytest.mark.pure
def test_ensure_backend_refuses_while_an_update_holds_the_flag(monkeypatch):
    calls = []
    held = MaintenanceFlag(
        pid=4242, started_at=datetime(2026, 9, 11, 10, 0), reason="update to head"
    )
    monkeypatch.setattr(mcp_stdio.maintenance, "active", lambda: held)
    monkeypatch.setattr(mcp_stdio, "probe_health", lambda c: calls.append("probe"))
    monkeypatch.setattr(mcp_stdio, "_spawn_backend", lambda c: calls.append("spawn"))

    with pytest.raises(RuntimeError) as refusal:
        mcp_stdio._ensure_backend(_cfg())

    assert "being updated" in str(refusal.value)
    assert "4242" in str(refusal.value)
    assert "update to head" in str(refusal.value)
    assert calls == []


@pytest.mark.pure
def test_open_home_respects_toggle(monkeypatch):
    opened = []
    monkeypatch.setattr(mcp_stdio.webbrowser, "open", lambda url: opened.append(url))
    mcp_stdio._open_home(_cfg(mcp_stdio_open_browser=False))
    assert opened == []
    mcp_stdio._open_home(_cfg(server_port=8080, mcp_stdio_open_browser=True))
    assert opened == ["http://127.0.0.1:8080/"]


@pytest.mark.pure
def test_build_proxy_targets_backend_mcp_url():
    proxy = mcp_stdio._build_proxy(_cfg(server_port=8080), "research")
    assert proxy.name == "research"


@pytest.mark.pure
def test_file_only_logging_omits_stdout_handler():
    """The shim's factory yields a logger with no stdout handler (file only) — stdout belongs to
    MCP."""
    import logging
    import sys

    from src.core.loggers.logger_store import LoggerStore

    try:
        mcp_stdio._use_file_only_logging(_cfg())
        handlers = LoggerStore.get("mcp")._logger.handlers
        assert any(isinstance(h, logging.FileHandler) for h in handlers)
        assert not any(
            type(h) is logging.StreamHandler and getattr(h, "stream", None) is sys.stdout
            for h in handlers
        )
    finally:
        LoggerStore.reset()


@pytest.mark.pure
def test_run_mcp_stdio_boots_backend_then_runs_proxy(monkeypatch):
    calls = []
    monkeypatch.setattr(mcp_stdio, "_use_file_only_logging", lambda c: None)
    monkeypatch.setattr(mcp_stdio, "_resolve_code", lambda c: "research")
    monkeypatch.setattr(mcp_stdio, "_ensure_backend", lambda c: calls.append("ensure"))

    class _FakeProxy:
        def run(self, show_banner):
            calls.append(("run", show_banner))

    monkeypatch.setattr(mcp_stdio, "_build_proxy", lambda c, code: _FakeProxy())
    mcp_stdio.run_mcp_stdio(_cfg())
    assert calls == ["ensure", ("run", False)]
