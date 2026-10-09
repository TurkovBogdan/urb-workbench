"""app: CLI flags, passing them into env (flag > env), role dispatch + migrate."""

from __future__ import annotations

import os
import sys
import types

import pytest

import app


def _fake_config(**over):
    """A lightweight Config stand-in for _run_server/_run_worker (no DB)."""
    base = dict(
        server_host="127.0.0.1", server_port=12200, app_log_level="INFO",
        server_hot_reload=False, server_processes=1,
        worker_modules_set=None, worker_max_concurrent_runs=10,
        worker_tick_seconds=5,
    )
    return types.SimpleNamespace(**{**base, **over})


@pytest.fixture
def _pin_role_env(monkeypatch):
    """Pin role-env to valid values so that main()'s direct writes are rolled back on teardown
    (monkeypatch restores the original)."""
    for key, val in (
        ("SERVER_ENABLED", "false"), ("WORKER_ENABLED", "false"),
        ("SERVER_HOT_RELOAD", "false"), ("WORKER_MODULES", ""),
        ("WORKER_TICK_SECONDS", "5"), ("WORKER_MAX_CONCURRENT_RUNS", "10"),
    ):
        monkeypatch.setenv(key, val)


@pytest.mark.pure
def test_parse_defaults_are_none():
    """No flags — every toggle is None (the role comes from env)."""
    a = app._parse_args([])
    assert a.backend is None
    assert a.worker is None
    assert a.hot_reload is None
    assert a.worker_module is None
    assert a.processes is None


@pytest.mark.pure
def test_parse_backend_worker_flags():
    a = app._parse_args(["--backend", "--worker"])
    assert a.backend is True
    assert a.worker is True


@pytest.mark.pure
def test_parse_negated_flags():
    a = app._parse_args(["--no-backend", "--no-hot-reload"])
    assert a.backend is False
    assert a.hot_reload is False


@pytest.mark.pure
def test_parse_mcp_stdio_flag():
    """Three states, and the role is told from its absence by ``is None``, not by truthiness.

    A bare flag yields an empty string — the role is on, and the server is found on its own. A
    check `if args.mcp_stdio` would take it for "no flag" and silently launch an ordinary process
    instead of the shim.
    """
    assert app._parse_args([]).mcp_stdio is None
    assert app._parse_args(["--mcp-stdio"]).mcp_stdio == ""
    assert app._parse_args(["--mcp-stdio", "workbench"]).mcp_stdio == "workbench"


@pytest.mark.pure
def test_parse_mcp_stdio_keeps_the_bare_form_before_another_flag():
    """`--mcp-stdio --mcp-workspace X` does not mean "the server is called --mcp-workspace"."""
    a = app._parse_args(["--mcp-stdio", "--mcp-workspace", "WORKSPACE@18e948522f"])

    assert a.mcp_stdio == ""
    assert a.mcp_workspace == "WORKSPACE@18e948522f"


@pytest.mark.pure
def test_mcp_flags_beat_env(monkeypatch):
    """Flag > env, as for the other roles; and both overrides are visible to the built Config."""
    monkeypatch.setenv("MCP_STDIO_CODE", "research")
    monkeypatch.setenv("MCP_WORKSPACE", "WORKSPACE@0000000000")
    monkeypatch.setattr(app, "_run_server", lambda c, a: None)
    seen = {}
    monkeypatch.setitem(
        sys.modules, "src.apps.app.mcp_stdio",
        types.SimpleNamespace(run_mcp_stdio=lambda cfg: seen.update(
            code=os.environ["MCP_STDIO_CODE"], workspace=os.environ["MCP_WORKSPACE"]
        )),
    )
    import src.core.config as cfg_mod

    monkeypatch.setattr(cfg_mod, "Config", lambda: types.SimpleNamespace())
    app.main(["--mcp-stdio", "workbench", "--mcp-workspace", "WORKSPACE@18e948522f"])

    assert seen == {"code": "workbench", "workspace": "WORKSPACE@18e948522f"}


@pytest.mark.pure
def test_bare_mcp_stdio_leaves_env_alone(monkeypatch):
    """A bare flag overrides nothing: an empty code would wipe the installation's setting."""
    monkeypatch.setenv("MCP_STDIO_CODE", "research")
    monkeypatch.setattr(app, "_run_server", lambda c, a: None)
    seen = {}
    monkeypatch.setitem(
        sys.modules, "src.apps.app.mcp_stdio",
        types.SimpleNamespace(run_mcp_stdio=lambda cfg: seen.update(
            code=os.environ["MCP_STDIO_CODE"]
        )),
    )
    import src.core.config as cfg_mod

    monkeypatch.setattr(cfg_mod, "Config", lambda: types.SimpleNamespace())
    app.main(["--mcp-stdio"])

    assert seen == {"code": "research"}


@pytest.mark.pure
def test_update_flags_default_to_the_safe_side():
    """No signals on circumstantial evidence and no changes: both `--dry-run` and
    `--stop-unregistered` (stopping processes with no registry record) are opt-in only."""
    plain = app._parse_args(["update"])
    assert (plain.dry_run, plain.stop_unregistered) == (False, False)
    assert app._parse_args(["update", "--stop-unregistered"]).stop_unregistered is True
    assert app._parse_args(["update", "--dry-run"]).dry_run is True


@pytest.mark.pure
def test_stop_is_a_subcommand_with_the_same_safe_defaults():
    """`stop` shuts the installation down rather than launching a process: it has its own pair of
    flags, both off by default — otherwise `./run.sh stop` would signal on circumstantial evidence."""
    plain = app._parse_args(["stop"])
    assert plain.command == "stop"
    assert (plain.dry_run, plain.stop_unregistered) == (False, False)
    assert app._parse_args(["stop", "--dry-run"]).dry_run is True
    assert app._parse_args(["stop", "--stop-unregistered"]).stop_unregistered is True
    assert app._launches_a_process(plain) is False


@pytest.mark.pure
def test_worker_module_is_repeatable():
    a = app._parse_args(["--worker-module", "alpha", "--worker-module", "beta"])
    assert a.worker_module == ["alpha", "beta"]


@pytest.mark.pure
def test_apply_env_overrides_sets_env(monkeypatch):
    for key in (
        "SERVER_ENABLED", "WORKER_ENABLED", "SERVER_HOT_RELOAD",
        "WORKER_MODULES", "WORKER_TICK_SECONDS", "WORKER_MAX_CONCURRENT_RUNS",
    ):
        monkeypatch.delenv(key, raising=False)
    args = app._parse_args(
        ["--backend", "--no-worker", "--worker-module", "a", "--worker-module", "b",
         "--worker-tick-seconds", "9", "--worker-max-concurrent", "3"]
    )
    app._apply_env_overrides(args)
    import os

    assert os.environ["SERVER_ENABLED"] == "true"
    assert os.environ["WORKER_ENABLED"] == "false"
    assert os.environ["WORKER_MODULES"] == "a,b"
    assert os.environ["WORKER_TICK_SECONDS"] == "9"
    assert os.environ["WORKER_MAX_CONCURRENT_RUNS"] == "3"


@pytest.mark.pure
def test_apply_env_overrides_skips_unset(monkeypatch):
    """None flags leave env alone (the previous value stays)."""
    monkeypatch.setenv("SERVER_ENABLED", "false")
    app._apply_env_overrides(app._parse_args([]))
    import os

    assert os.environ["SERVER_ENABLED"] == "false"


@pytest.mark.pure
def test_host_port_pushed_to_env_processes_not(monkeypatch):
    """--host/--port reach env, so the running app knows its real address (the settings page
    predicts a move from it); --processes goes straight to _run_server."""
    for key in ("SERVER_HOST", "SERVER_PORT", "SERVER_PROCESSES"):
        # setenv first: delenv of an absent key records nothing to restore, and the direct
        # os.environ writes below would outlive the test.
        monkeypatch.setenv(key, "")
        monkeypatch.delenv(key)
    app._apply_env_overrides(
        app._parse_args(["--host", "0.0.0.0", "--port", "9", "--processes", "4"])
    )
    import os

    assert os.environ["SERVER_HOST"] == "0.0.0.0"
    assert os.environ["SERVER_PORT"] == "9"
    assert "SERVER_PROCESSES" not in os.environ


# ── env → Config (flag > env > default) ─────────────────────────────────────


@pytest.mark.pure
def test_env_drives_role_in_config(monkeypatch):
    """env toggles reach Config (env > default)."""
    monkeypatch.setenv("SERVER_ENABLED", "false")
    monkeypatch.setenv("WORKER_ENABLED", "true")
    from src.core.config import Config

    c = Config(_env_file=None, db_host="x", db_name="x", db_user="x",
               db_password="x", db_ssl=False)
    assert c.server_enabled is False
    assert c.worker_enabled is True


@pytest.mark.pure
def test_flag_overrides_env(monkeypatch):
    """A flag overrides env: SERVER_ENABLED=false + --backend → true."""
    monkeypatch.setenv("SERVER_ENABLED", "false")
    app._apply_env_overrides(app._parse_args(["--backend"]))
    import os

    assert os.environ["SERVER_ENABLED"] == "true"


# ── main(): role dispatch ────────────────────────────────────────────────────


@pytest.mark.pure
def test_main_both_disabled_clean_exit(monkeypatch, _pin_role_env):
    """Neither SERVER nor WORKER → NOT an error: a clean exit (None), nothing launched."""
    calls = []
    monkeypatch.setattr(app, "_run_server", lambda c, a: calls.append("server"))
    monkeypatch.setattr(app.asyncio, "run", lambda c: calls.append("worker"))
    assert app.main(["--no-backend", "--no-worker"]) is None
    assert calls == []


@pytest.mark.pure
def test_main_dispatches_to_server(monkeypatch, _pin_role_env):
    """server_enabled → _run_server; the worker branch is left alone."""
    calls = []
    monkeypatch.setattr(app, "_run_server", lambda c, a: calls.append("server"))
    monkeypatch.setattr(app.asyncio, "run", lambda c: calls.append("worker"))
    app.main(["--backend", "--no-worker"])
    assert calls == ["server"]


@pytest.mark.pure
def test_main_pure_worker_runs_lifespan(monkeypatch, _pin_role_env):
    """Worker only → NOT _run_server, but asyncio.run(_run_worker)."""
    calls = []
    monkeypatch.setattr(app, "_run_server", lambda c, a: calls.append("server"))

    def fake_run(coro):
        calls.append("worker")
        coro.close()  # avoid "coroutine never awaited"

    monkeypatch.setattr(app.asyncio, "run", fake_run)
    app.main(["--no-backend", "--worker"])
    assert calls == ["worker"]


@pytest.mark.pure
def test_main_pure_worker_hot_reload_branch(monkeypatch, _pin_role_env):
    """Worker only + hot-reload → the watch supervisor, NOT a direct asyncio.run."""
    calls = []
    monkeypatch.setattr(app, "_run_worker_hot_reload", lambda: calls.append("watch"))
    monkeypatch.setattr(app.asyncio, "run", lambda c: calls.append("worker"))
    app.main(["--no-backend", "--worker", "--hot-reload"])
    assert calls == ["watch"]


@pytest.mark.pure
def test_run_worker_hot_reload_spawns_no_reload_child(monkeypatch):
    """_run_worker_hot_reload watches src/ and restarts the worker with --no-hot-reload."""
    rec = {}
    monkeypatch.setitem(
        sys.modules, "watchfiles",
        types.SimpleNamespace(run_process=lambda *a, **k: rec.update(paths=a, target=k["target"])),
    )
    app._run_worker_hot_reload()
    assert rec["paths"] and rec["paths"][0].endswith("/src")
    assert "--worker" in rec["target"]
    assert "--no-backend" in rec["target"]
    assert "--no-hot-reload" in rec["target"]


# ── _run_server: reload vs processes ─────────────────────────────────────────


@pytest.mark.pure
def test_run_server_hot_reload_branch(monkeypatch):
    """server_hot_reload=true → uvicorn reload=True, workers is NOT passed."""
    rec = {}
    monkeypatch.setitem(
        sys.modules, "uvicorn",
        types.SimpleNamespace(run=lambda *a, **k: rec.update(a=a, k=k)),
    )
    cfg = _fake_config(server_hot_reload=True, server_processes=4)
    app._run_server(cfg, app._parse_args([]))
    assert rec["k"].get("reload") is True
    assert "workers" not in rec["k"]


@pytest.mark.pure
def test_run_server_processes_branch(monkeypatch):
    """server_hot_reload=false → uvicorn workers=N, reload is NOT passed."""
    rec = {}
    monkeypatch.setitem(
        sys.modules, "uvicorn",
        types.SimpleNamespace(run=lambda *a, **k: rec.update(a=a, k=k)),
    )
    cfg = _fake_config(server_hot_reload=False, server_processes=4)
    app._run_server(cfg, app._parse_args([]))
    assert rec["k"].get("workers") == 4
    assert "reload" not in rec["k"]


@pytest.mark.pure
def test_run_server_binds_config_address_and_cli_processes(monkeypatch):
    """The address comes from Config (--host/--port arrive there through env); --processes
    overrides the config value directly."""
    rec = {}
    monkeypatch.setitem(
        sys.modules, "uvicorn",
        types.SimpleNamespace(run=lambda *a, **k: rec.update(a=a, k=k)),
    )
    cfg = _fake_config(server_host="0.0.0.0", server_port=9, server_processes=1)
    args = app._parse_args(["--processes", "7"])
    app._run_server(cfg, args)
    assert rec["k"]["host"] == "0.0.0.0"
    assert rec["k"]["port"] == 9
    assert rec["k"]["workers"] == 7


# ── _run_worker: worker scope ────────────────────────────────────────────────


@pytest.mark.pure
async def test_run_worker_configures_scope(monkeypatch):
    """_run_worker forces the ticker via configure_worker with scope/knobs from config."""
    rec = {}
    from src.core import scheduler

    monkeypatch.setattr(scheduler, "configure_worker", lambda **k: rec.update(k))
    monkeypatch.setattr("src.apps.app.modules.build_modules", lambda: [])

    class _Boom(Exception):
        pass

    import src.core.app_factory as af

    def _boom(**_):
        raise _Boom

    monkeypatch.setattr(af, "create_app", _boom)

    cfg = _fake_config(
        worker_modules_set=frozenset({"alpha"}),
        worker_max_concurrent_runs=3, worker_tick_seconds=9,
    )
    with pytest.raises(_Boom):
        await app._run_worker(cfg)
    assert rec == {"modules": frozenset({"alpha"}), "max_concurrent": 3, "tick": 9}


# ── the migrate subcommand ───────────────────────────────────────────────────


@pytest.mark.pure
def test_parse_no_command_is_run():
    """No subcommand → command=None (launch mode)."""
    assert app._parse_args([]).command is None
    assert app._parse_args(["--backend"]).command is None


@pytest.mark.pure
def test_parse_migrate_default_action_is_check():
    a = app._parse_args(["migrate"])
    assert a.command == "migrate"
    assert a.action == "check"


@pytest.mark.pure
def test_parse_migrate_upgrade():
    a = app._parse_args(["migrate", "upgrade"])
    assert a.command == "migrate"
    assert a.action == "upgrade"


@pytest.mark.pure
def test_parse_migrate_rejects_unknown_action():
    with pytest.raises(SystemExit):
        app._parse_args(["migrate", "nope"])


@pytest.mark.pure
def test_main_dispatches_to_mcp_stdio(monkeypatch):
    """`--mcp-stdio` → run_mcp_stdio, bypassing server/worker and role-env."""
    calls = []
    monkeypatch.setattr(app, "_run_server", lambda c, a: calls.append("server"))
    monkeypatch.setattr(app.asyncio, "run", lambda c: calls.append("worker"))
    monkeypatch.setitem(
        sys.modules, "src.apps.app.mcp_stdio",
        types.SimpleNamespace(run_mcp_stdio=lambda cfg: calls.append("mcp-stdio")),
    )
    import src.core.config as cfg_mod

    monkeypatch.setattr(cfg_mod, "Config", lambda: types.SimpleNamespace())
    assert app.main(["--mcp-stdio"]) is None
    assert calls == ["mcp-stdio"]


@pytest.mark.pure
def test_main_dispatches_to_migrate(monkeypatch):
    """`migrate` → asyncio.run(_run_migrate), without launching the server/worker."""
    calls = []
    monkeypatch.setattr(app, "_run_server", lambda c, a: calls.append("server"))

    def fake_run(coro):
        calls.append("migrate")
        coro.close()
        return 0

    monkeypatch.setattr(app.asyncio, "run", fake_run)
    assert app.main(["migrate", "upgrade"]) == 0
    assert calls == ["migrate"]
