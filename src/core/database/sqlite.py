"""SQLite engine settings: connection pragmas and transaction intent.

Applied on the ``connect`` event rather than once at startup: connection-level settings
do not survive a reconnect, and the pool hands out new connections and reused ones
alike. Under the async engine the listener hangs on ``engine.sync_engine`` — it cannot
be attached to the ``AsyncEngine`` itself.

``journal_mode`` is written into the database file header (repeating it on every
connection is harmless); the other knobs live inside the connection. The journal mode is
not a command but a request: it returns the mode **actually** in effect, and the switch
can fail to happen without any error, so the result is read back and a mismatch is
logged.

There is deliberately no lock-wait pragma here: ``busy_timeout`` is set by the driver's
``timeout`` parameter (``Config.engine_kwargs``). ``synchronous = NORMAL`` is a
deliberate durability choice: in WAL mode an application crash loses nothing committed;
the difference from ``FULL`` shows only on an OS crash.

**Transaction intent.** A transaction that began with a read cannot be promoted to a
write: its snapshot may have drifted from the database, and the engine refuses — on a
non-blocking lock, bypassing ``busy_timeout``, so a retry does not help. So a writing
transaction declares itself as writing when it opens: the driver is forbidden to emit
``BEGIN`` itself (``isolation_level = None``), and on the ``begin`` event ``BEGIN
IMMEDIATE`` is emitted for transactions marked with ``WRITE_EXECUTION_OPTIONS`` (set by
``database.write_scope``). A forgotten mark is caught by a guard: a mutating statement in
a read transaction is an error, not a silent landmine. The guard works on any database;
the open interception only on a file-backed one (the reason is next to the interception).
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import event
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import AsyncEngine

from src.core.config import Config
from src.core.loggers import get_logger

_LOG = get_logger()

_JOURNAL_MODE = "wal"
_VIOLATIONS_IN_MESSAGE = 10
_WRITE_OPTION = "writing_transaction"
_REPORTED_PRAGMAS = ("journal_mode", "synchronous", "foreign_keys")
_MUTATING_STATEMENTS = ("INSERT", "UPDATE", "DELETE", "REPLACE")

WRITE_EXECUTION_OPTIONS = {_WRITE_OPTION: True}

_CONNECTION_PRAGMAS: tuple[str, ...] = (
    "PRAGMA foreign_keys = ON",
    "PRAGMA synchronous = NORMAL",
    "PRAGMA temp_store = MEMORY",
    "PRAGMA cache_size = -64000",
    "PRAGMA journal_size_limit = 67108864",
)


def connection_pragmas(config: Config) -> tuple[str, ...]:
    """The pragmas every new connection receives under the current provider.

    An in-memory database does not request a journal mode: it always answers ``memory``,
    and asking it for WAL is a guaranteed mismatch in the log.
    """
    if config.db_provider != "sqlite":
        return ()
    if config.sqlite_in_memory:
        return _CONNECTION_PRAGMAS
    return (f"PRAGMA journal_mode = {_JOURNAL_MODE.upper()}", *_CONNECTION_PRAGMAS)


def configure_sqlite(engine: AsyncEngine, config: Config) -> None:
    """Attach the SQLite settings to the engine; a no-op for other providers."""
    pragmas = connection_pragmas(config)
    if not pragmas:
        return
    expected_journal_mode = None if config.sqlite_in_memory else _JOURNAL_MODE

    reported = False

    @event.listens_for(engine.sync_engine, "connect")
    def apply_connection_pragmas(dbapi_connection, connection_record) -> None:
        nonlocal reported
        cursor = dbapi_connection.cursor()
        try:
            for statement in pragmas:
                cursor.execute(statement)
                cursor.fetchall()
            effective = {name: _read(cursor, name) for name in _REPORTED_PRAGMAS}
            if not reported:
                # Defaults are fixed when SQLite itself is compiled, so the log gets the
                # values read back, not the ones we asked for.
                _LOG.info("sqlite: %s", effective)
                reported = True
            if expected_journal_mode is None:
                return
            if str(effective["journal_mode"]).lower() != expected_journal_mode:
                _LOG.warning(
                    "sqlite: journal mode did not switch — requested %s, in effect %s",
                    expected_journal_mode,
                    effective["journal_mode"],
                )
        finally:
            cursor.close()

    # An in-memory database lives in a single driver connection (StaticPool) shared by
    # all sessions: intercepting the transaction open there is impossible — a second
    # session would get "cannot start a transaction within a transaction". There is no
    # lone writer in memory anyway, so there is no one to declare intent to.
    if not config.sqlite_in_memory:

        @event.listens_for(engine.sync_engine, "connect")
        def take_over_transaction_start(dbapi_connection, connection_record) -> None:
            dbapi_connection.isolation_level = None

        @event.listens_for(engine.sync_engine, "begin")
        def begin_with_declared_intent(connection: Connection) -> None:
            writing = connection.get_execution_options().get(_WRITE_OPTION, False)
            connection.exec_driver_sql("BEGIN IMMEDIATE" if writing else "BEGIN")

    @event.listens_for(engine.sync_engine, "before_cursor_execute")
    def require_declared_write_intent(
        connection: Connection, cursor, statement, parameters, context, executemany
    ) -> None:
        if not statement.lstrip().upper().startswith(_MUTATING_STATEMENTS):
            return
        if connection.get_execution_options().get(_WRITE_OPTION, False):
            return
        raise RuntimeError(
            "sqlite: mutating statement in a read transaction — use write_scope() "
            f"instead of session_scope(): {statement.strip()[:120]}"
        )


@contextmanager
def foreign_keys_disabled(connection: Connection) -> Iterator[None]:
    """Disable foreign-key enforcement while the schema changes (SQLite; otherwise a no-op).

    Recreating a table (a batch migration) goes through dropping the old one, and with
    enforcement on, dropping a table implicitly deletes all its rows — and the foreign-key
    actions on that delete fire for real: children vanish in a cascade, while the
    migration reports success.

    The switch must be flipped outside a transaction: inside one it silently does nothing,
    with no error or warning. So the pragma bypasses SQLAlchemy and goes straight to the
    driver connection, before the migration transaction begins.
    """
    if connection.dialect.name != "sqlite":
        yield
        return
    if not _switch_foreign_keys(connection, enabled=False):
        raise RuntimeError(
            "sqlite: could not turn off foreign-key enforcement — the switch has no effect "
            "inside an open transaction; turn it off before the connection's first statement"
        )
    body_failed = False
    try:
        yield
        _raise_on_foreign_key_violations(connection)
    except BaseException:
        body_failed = True
        raise
    finally:
        # Enforcement can only be restored outside a transaction, and alembic leaves open the
        # one in which it read the version table (visible when there is nothing to apply).
        _close_transaction(connection, rollback=body_failed)
        if not _switch_foreign_keys(connection, enabled=True):
            # A connection with enforcement off must not return to the pool.
            _LOG.error("sqlite: foreign-key enforcement not restored — connection discarded")
            connection.invalidate()


def _close_transaction(connection: Connection, *, rollback: bool) -> None:
    if not connection.in_transaction():
        return
    connection.rollback() if rollback else connection.commit()


def _read(cursor, pragma: str):
    cursor.execute(f"PRAGMA {pragma}")
    return cursor.fetchone()[0]


def foreign_keys_enabled(connection: Connection) -> bool:
    """Whether foreign-key enforcement is on for this connection (read from the driver)."""
    cursor = _driver_cursor(connection)
    try:
        cursor.execute("PRAGMA foreign_keys")
        return bool(cursor.fetchone()[0])
    finally:
        cursor.close()


def _driver_cursor(connection: Connection):
    """A driver cursor — bypassing SQLAlchemy's transaction bookkeeping."""
    return connection.connection.dbapi_connection.cursor()


def _switch_foreign_keys(connection: Connection, *, enabled: bool) -> bool:
    """Flip enforcement and make sure the flip took effect.

    Inside an open transaction the pragma is a silent no-op, so the only way to learn the
    result is to read it back.
    """
    cursor = _driver_cursor(connection)
    try:
        cursor.execute(f"PRAGMA foreign_keys = {'ON' if enabled else 'OFF'}")
    finally:
        cursor.close()
    return foreign_keys_enabled(connection) is enabled


def _raise_on_foreign_key_violations(connection: Connection) -> None:
    cursor = _driver_cursor(connection)
    try:
        cursor.execute("PRAGMA foreign_key_check")
        violations = cursor.fetchall()
    finally:
        cursor.close()
    if violations:
        raise RuntimeError(
            f"sqlite: migrations left referential integrity violations ({len(violations)}): "
            f"{violations[:_VIOLATIONS_IN_MESSAGE]}"
        )


__all__ = [
    "WRITE_EXECUTION_OPTIONS",
    "configure_sqlite",
    "connection_pragmas",
    "foreign_keys_disabled",
    "foreign_keys_enabled",
]
