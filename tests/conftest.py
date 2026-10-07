"""Shared test fixtures and the forced override onto an in-memory DB.

Tests run on SQLite entirely in RAM (``DB_PROVIDER=sqlite``, ``DB_PATH=:memory:``)
— no external Postgres server and no credential pools. The ``DB_*`` env variables
are overridden BEFORE the first imports from ``src``, so that any ``Config()``
in any test gets the test database. This is the single point of protection — you
cannot accidentally hit the dev/prod DB.

Isolation of a parallel run is free: each xdist worker is a separate process
with its own in-memory database; each test's schema is built from the ORM models
(``create_all`` in the lifespan or in a local ``db`` fixture) on a fresh engine.

Heavy Alembic migration tests (``postgresql.*`` column types) do not run on SQLite —
they are skipped until a real Postgres is given via ``TEST_PG_DSN``
(``postgresql://user:pass@host:port/dbname``); see ``pytest_collection_modifyitems``.
The DSN database is only an administrative connection: for each heavy test the
``_own_postgres_database_for_heavy`` fixture creates its own disposable database alongside and
drops it afterwards, while the other tests of the same run stay on in-memory SQLite.
"""

from __future__ import annotations

# ── env override. Must happen before imports from src ───────────────────────
import os
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlsplit

_PROJECT_ROOT = Path(__file__).resolve().parent.parent

# ``TEST_PG_DSN`` (optional) enables the heavy migration tests: it does not "switch the run to
# Postgres", it provides an administrative connection from which each heavy test gets its own
# database (see ``_own_postgres_database_for_heavy``). Everything else stays on in-memory SQLite.
_PG_DSN = os.environ.get("TEST_PG_DSN")
os.environ["DB_PROVIDER"] = "sqlite"
os.environ["DB_PATH"] = ":memory:"
os.environ["DB_SSL"] = "false"

os.environ["WORKER_ENABLED"] = "false"
# Tests bring up the HTTP API — enable zone mounting (default false = worker-only).
os.environ["SERVER_ENABLED"] = "true"
# CORS origins are built from server_vite_port; set it so the preflight test sees an origin.
os.environ["SERVER_VITE_PORT"] = "13406"
# Tests write all runtime artifacts to ``runtime/test/`` (logs, cache, user).
# AppPath reads ``APP_ENV`` → override it before the first imports from src.
os.environ["APP_ENV"] = "test"

# ── From here on src may be imported ────────────────────────────────────────
import pytest  # noqa: E402

from src.core.config import Config, get_config  # noqa: E402
from src.core.database import close_database  # noqa: E402
from src.core.loggers import LoggerStore  # noqa: E402

# ── Convenience alias flags instead of ``-m`` ────────────────────────────────
# By default (no flags) ``addopts`` keeps only the unmarked tests.
# A flag enables the matching group; several flags are combined with OR.
# ``--all`` lifts the filter entirely. The flags override ``-m``.
_GROUP_FLAGS = ("pure", "db", "heavy", "live")

# ── Area flags (path to the tests) ───────────────────────────────────────────
# Test type (marker) and area (directory) are orthogonal: ``--core``/``--module``
# set WHERE to look, marker flags set WHAT to run. Sugar over positional
# paths (``--core`` = ``tests/core tests/apps``) with module name validation.
_CORE_PATHS = ("tests/core", "tests/apps")
_MODULES_DIR = _PROJECT_ROOT / "tests" / "modules"


def pytest_addoption(parser):
    group = parser.getgroup("group selection")
    for name in _GROUP_FLAGS:
        group.addoption(
            f"--{name}", action="store_true", default=False,
            help=f"include tests marked @pytest.mark.{name}",
        )
    group.addoption(
        "--all", action="store_true", default=False,
        help="run all tests (lift the marker filter)",
    )
    group.addoption(
        "--unmarked", action="store_true", default=False,
        help="only \"lost\" tests — those without a type marker (pure/db/heavy/live)",
    )
    area = parser.getgroup("area selection")
    area.addoption(
        "--core", action="store_true", default=False,
        help="only the core tests (tests/core + tests/apps)",
    )
    area.addoption(
        "--module", action="append", default=[], metavar="NAME[,NAME...]",
        help="only the tests of module tests/modules/NAME; comma-separated list "
             "and/or a repeated flag",
    )
    # Deprecated: in-memory SQLite has no pool of physical databases, worker isolation
    # is free. The option is kept as a no-op so that old commands don't fail.
    parser.getgroup("xdist").addoption(
        "--dbs", action="store", default=None, metavar="1,3,5-8",
        help="deprecated and ignored (tests run on in-memory SQLite, there is no DB pool)",
    )


def _resolve_area_paths(config) -> list[str]:
    """Directories from the ``--core``/``--module`` flags; ``[]`` if neither is given."""
    if not config.option.core and not config.option.module:
        return []
    if config.option.file_or_dir:
        raise pytest.UsageError(
            "--core/--module cannot be combined with an explicit test path"
        )
    paths: list[str] = []
    if config.option.core:
        paths.extend(str(_PROJECT_ROOT / p) for p in _CORE_PATHS)
    # ``--module`` takes a comma-separated list and may be repeated:
    # ``--module=core_users,core_storage`` ≡ ``--module=core_users --module=core_storage``.
    names = [
        n.strip()
        for spec in config.option.module
        for n in spec.split(",")
        if n.strip()
    ]
    for name in names:
        target = _MODULES_DIR / name
        if not target.is_dir():
            available = sorted(
                p.name for p in _MODULES_DIR.iterdir()
                if p.is_dir() and not p.name.startswith("__")
            )
            raise pytest.UsageError(
                f"unknown module '{name}'. Available: {', '.join(available)}"
            )
        paths.append(str(target))
    return paths


# ── Parallel run ─────────────────────────────────────────────────────────────
# Each xdist worker is a separate process with its own in-memory SQLite, so
# db/heavy are isolated and parallelise freely without any DB pool.


@pytest.hookimpl(tryfirst=True)
def pytest_cmdline_main(config) -> None:
    """Parallelise by core count by default (``-n auto``).

    Set here rather than in ``pytest_configure``: xdist reads ``numprocesses`` in
    its own ``pytest_cmdline_main`` (before ``configure``) and would not pick up a
    later value.

    * ``-n`` not given → ``-n auto`` (by core count; each worker has its own in-memory DB);
    * an explicit ``-n``/``-n0`` is left as is (``-n0`` = inprocess for ``--pdb``).

    Nothing is touched inside a worker.
    """
    if os.environ.get("PYTEST_XDIST_WORKER"):
        return
    if not hasattr(config.option, "numprocesses"):  # xdist is not installed
        return
    if config.option.numprocesses is None:
        config.option.numprocesses = "auto"


def pytest_configure(config):
    area_paths = _resolve_area_paths(config)
    if area_paths:
        config.args[:] = area_paths
    if config.option.all:
        config.option.markexpr = ""
    elif config.option.unmarked:
        # "Lost" tests: no type marker at all. Every test must carry exactly
        # one — this filter catches those that didn't get it (a standards audit).
        config.option.markexpr = " and ".join(f"not {n}" for n in _GROUP_FLAGS)
    else:
        chosen = [name for name in _GROUP_FLAGS if getattr(config.option, name)]
        if chosen:
            config.option.markexpr = " or ".join(chosen)


def pytest_collection_modifyitems(config, items):
    """Heavy Alembic tests need Postgres — skip them until ``TEST_PG_DSN`` is set.

    The migrations are written in ``postgresql.*`` types (JSONB/TIMESTAMP) and do not
    apply on SQLite.
    """
    if _PG_DSN:
        return
    skip_pg = pytest.mark.skip(
        reason="heavy migration tests need Postgres — set TEST_PG_DSN"
    )
    for item in items:
        if item.get_closest_marker("heavy") is not None:
            item.add_marker(skip_pg)


# ── Heavy tier isolation: one database per test ──────────────────────────────

_DISPOSABLE_DATABASE_PREFIX = "urb_test_"


def _postgres_environment(admin_dsn: str, database: str) -> dict[str, str]:
    """``DB_*`` for ``Config``: credentials and host from the admin DSN, the database its own."""
    parts = urlsplit(admin_dsn)
    return {
        "DB_PROVIDER": "postgres",
        "DB_HOST": parts.hostname or "127.0.0.1",
        "DB_PORT": str(parts.port or 5432),
        "DB_NAME": database,
        "DB_USER": parts.username or "",
        "DB_PASSWORD": parts.password or "",
        "DB_SSL": "false",
    }


@asynccontextmanager
async def _disposable_database(admin_dsn: str):
    """A fresh database under a unique name — created before the block, dropped after it.

    ``WITH (FORCE)`` severs connections the test may have left open: without it ``DROP``
    refuses, and the database is left hanging on the server.
    """
    import asyncpg

    database = f"{_DISPOSABLE_DATABASE_PREFIX}{uuid.uuid4().hex[:12]}"
    admin = await asyncpg.connect(admin_dsn)
    try:
        await admin.execute(f'CREATE DATABASE "{database}"')
    finally:
        await admin.close()
    try:
        yield database
    finally:
        admin = await asyncpg.connect(admin_dsn)
        try:
            await admin.execute(f'DROP DATABASE IF EXISTS "{database}" WITH (FORCE)')
        finally:
            await admin.close()


@pytest.fixture(autouse=True)
async def _own_postgres_database_for_heavy(request, monkeypatch):
    """Each heavy test runs on its own freshly created PostgreSQL database.

    A shared database works in neither mode: under ``-n auto`` workers race on
    ``CREATE TABLE``; under ``-n0`` a test that stamped a synthetic revision from ``tmp_path``
    leaves a row the next runner can no longer resolve. A database per test covers both
    cases. For non-heavy tests the fixture does nothing.
    """
    is_heavy = request.node.get_closest_marker("heavy") is not None
    if not is_heavy or not _PG_DSN:
        yield
        return
    async with _disposable_database(_PG_DSN) as database:
        for key, value in _postgres_environment(_PG_DSN, database).items():
            monkeypatch.setenv(key, value)
        get_config.cache_clear()
        try:
            yield
        finally:
            await close_database()


@pytest.fixture(autouse=True)
def _registry_outside_the_checkout(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """The process registry goes into a temp directory for EVERY test.

    `app.main()` declares the process in `runtime/processes/`, and the role tests call exactly
    that: without the override a run would record pytest as an installation process, and the next
    updater on this machine would get it in its stop plan.
    """
    from src.core import process_registry

    monkeypatch.setattr(process_registry, "project_root", lambda: tmp_path)


@pytest.fixture(autouse=True)
def _reset_logger_store():
    """Reset the channels between tests so that one doesn't leak into another."""
    yield
    LoggerStore.reset()


@pytest.fixture(autouse=True)
def _clear_settings_cache():
    """`get_config` caches — reset its lru_cache between config tests."""
    get_config.cache_clear()
    yield
    get_config.cache_clear()


@pytest.fixture(autouse=True)
async def _dispose_engine_between_tests(request):
    """Close the module-level engine after every db test.

    On in-memory SQLite a clean start is guaranteed by itself: each db test
    (or lifespan) creates a new engine via ``init_database`` → a new empty
    ``:memory:`` database, and ``init_database`` disposes of the previous one. This
    teardown only cleans up a dangling engine so it doesn't leak between tests.

    Skipped for ``@pytest.mark.pure``: those tests don't touch the DB.
    """
    yield
    if request.node.get_closest_marker("pure") is not None:
        return
    await close_database()


@pytest.fixture
def config() -> Config:
    """Test ``Config`` (in-memory SQLite; for a heavy test, its disposable PostgreSQL database)."""
    return Config()
