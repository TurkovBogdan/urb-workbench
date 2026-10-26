"""`app.py restore <copy>`: put back a copy taken by `app.py backup` — the database and the stored
files together — and move what stands there now aside instead of deleting it.

A copy is restored whole or not at all, because half of one is the gap the copy exists to close:
a base whose files are gone, or files no base counts. So everything new is first prepared next to
its place — the database file beside the current one, the file tree beside the storage root — and
only then swapped in by renaming. A failed preparation changes nothing (`RestoreRefused`); a swap
that fails is undone (`RestoreRefused` too); only an undo that fails, or a PostgreSQL restore
failing after the schema was dropped, leaves the install half-restored (`RestoreBroken`), and the
message names where every piece is.

A refusal leaves no trace: what the run prepared, the folders it made for that, and the dump of
a PostgreSQL base nothing touched go again. It removes only its own: every name it would create
carries its stamp and must be free when it begins, or it refuses before making anything. Ctrl-C
is a refusal like any other until the schema reset is sent; a reset that got no answer — a lost
connection, Ctrl-C — may or may not have emptied the schema, so the files go back, the dump stays,
and it is `RestoreBroken`.

A copy whose files changed after it was taken is refused the same way. The tree prepared beside
the storage root — exactly what would be swapped in — is checked against the copy's inventory
(`src/core/backup_inventory.py`) before anything moves: a file missing, of another size or not in
the inventory is a refusal naming each one. `app.py backup --verify <copy>` runs the same checks
without restoring anything.

The install must be down: the maintenance flag goes up first, so the MCP bridge does not bring a
backend up midway, and then the same stop plan as `app.py stop` must find nothing running. The
command never stops the install itself — replacing a base under a writer is what it guards
against, and whoever runs it decides when the install goes down.

What stands there now is kept: a SQLite base moves aside with its sidecars as
`<base>.before-restore.<stamp>` (still an openable database with its journal), the storage root
as `<root>.before-restore.<stamp>`; a PostgreSQL base is dumped to
`runtime/<env>/backup/<db>.before-restore.<stamp>.dump` before its schema is dropped.

PostgreSQL is restored into an empty `public` schema rather than with `pg_restore --clean`: the
latter drops only what the archive holds, so a table made by a migration after the copy would
survive and break that migration when it runs again.
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import sys
from collections.abc import Iterable, Iterator
from contextlib import contextmanager, suppress
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import NoReturn

from src.core import maintenance
from src.core.app_path import resolve_runtime_root
from src.core.backup import (
    BACKUP_FOLDER_NAME,
    MANIFEST_FORMAT,
    MANIFEST_NAME,
    STAMP_FORMAT,
    STORAGE_DIR_NAME,
    BackupRefused,
    TreeSnapshot,
    check_sqlite_file,
    connect_postgres,
    dump_postgres,
    first_ctrl_c_only,
    list_postgres_archive,
    make_parents,
    postgres_connection,
    postgres_environment,
    remove_made,
    remove_tree,
    require_tool,
    resolve_path,
    run_tool,
    sigint_ignored,
    snapshot_tree,
    sqlite_source,
)
from src.core.backup_inventory import (
    Expected,
    InventoryUnusable,
    differences,
    expected_files,
    read_regular_file,
    scan_tree,
)
from src.core.config import Config
from src.core.maintenance import MaintenanceHeld
from src.core.update.stop import plan_live_stop

EXIT_RESTORED = 0
EXIT_REFUSED = 1
EXIT_HALF_RESTORED = 2

EXIT_WHOLE = 0
EXIT_NOT_WHOLE = 1

# What SQLite keeps beside a base: a journal it would replay over a base that is not its own.
SQLITE_SIDECARS = ("-wal", "-shm", "-journal")
ASIDE_MARK = "before-restore"
STAGED_MARK = "restoring"
INTERRUPTED = "interrupted (Ctrl-C)"

_RESET_SCHEMA = "DROP SCHEMA public CASCADE; CREATE SCHEMA public"


class RestoreRefused(RuntimeError):
    """Nothing of the install was changed; the message is what the operator reads."""


class RestoreBroken(RuntimeError):
    """The swap stopped midway and could not be undone; the message says where everything is."""


@dataclass(frozen=True)
class Manifest:
    """What `backup.json` says the copy holds, its paths resolved inside the copy. ``expected`` —
    what its tree of stored files must hold; ``None`` with ``storage``: the copy has no files."""

    directory: Path
    provider: str
    database: Path
    revisions: tuple[str, ...]
    storage: Path | None
    created_at: str
    expected: Expected | None = None


@dataclass
class RestoreReport:
    copy: Path
    database: str
    files: TreeSnapshot
    aside: list[str] = field(default_factory=list)
    checked: str = "no stored files in the copy"

    def describe(self) -> str:
        kept = [f"  {line}" for line in self.aside] or ["  (nothing stood there)"]
        return "\n".join(
            [
                f"restored:  {self.copy}",
                f"database:  {self.database}",
                f"storage:   {self.files.describe()}",
                f"checked:   {self.checked}",
                "the previous state is kept aside:",
                *kept,
                "check the files against the base: uv run python src/app.py storage check",
            ]
        )


def read_manifest(directory: Path) -> Manifest:
    """The copy's description, or a refusal: a directory without `backup.json` is not a copy —
    `backup` writes it last, so its absence is also what a copy cut short looks like."""
    path = directory / MANIFEST_NAME
    try:
        payload = json.loads(read_regular_file(path))
    except FileNotFoundError:
        raise RestoreRefused(
            f"{directory} is not a copy taken by `app.py backup` — there is no {MANIFEST_NAME}"
        ) from None
    except (OSError, ValueError, RecursionError) as failure:
        raise RestoreRefused(f"{path} cannot be read: {failure}") from failure
    if not isinstance(payload, dict) or payload.get("format") != MANIFEST_FORMAT:
        raise RestoreRefused(f"{path} is of a format this command does not know")
    try:
        storage = payload["storage"]
        if storage is not None and not isinstance(storage, dict):
            raise RestoreRefused(f"{path}: storage is not a description of the stored files")
        return Manifest(
            directory=directory,
            provider=str(payload["provider"]),
            database=directory / str(payload["database"]),
            revisions=tuple(str(revision) for revision in payload.get("revisions", ())),
            storage=None if storage is None else directory / STORAGE_DIR_NAME,
            created_at=str(payload.get("created_at", "")),
            expected=None if storage is None else expected_files(directory, storage),
        )
    except (KeyError, TypeError) as failure:
        raise RestoreRefused(f"{path} lacks {failure}") from failure
    except InventoryUnusable as failure:
        raise RestoreRefused(str(failure)) from failure


def restore(config: Config, copy: Path, *, stamp: str | None = None) -> RestoreReport:
    """Put the copy back, or refuse having changed nothing (see the module docstring). Ctrl-C is
    a refusal like any other while nothing has moved, and an undone swap after it."""
    with _interrupt_refuses("the copy was being checked"):
        manifest = read_manifest(resolve_path(copy))
        _verify_copy(config, manifest)
        try:
            maintenance.begin(f"restore {manifest.directory}")
        except MaintenanceHeld as held:
            raise RestoreRefused(f"the install is under maintenance: {held}") from held
        except OSError as failure:
            maintenance.end()
            raise RestoreRefused(f"the maintenance flag cannot be raised: {failure}") from failure
    try:
        with _interrupt_refuses("the install was being checked"):
            _refuse_if_running()
        return _restore_stopped(config, manifest, stamp or datetime.now().strftime(STAMP_FORMAT))
    finally:
        with sigint_ignored():
            maintenance.end()


@contextmanager
def _interrupt_refuses(doing: str) -> Iterator[None]:
    try:
        yield
    except KeyboardInterrupt:
        raise RestoreRefused(f"{INTERRUPTED} while {doing}") from None


def restore_command(copy: str) -> int:
    """`app.py restore <copy>`: the report on stdout, a refusal on stderr."""
    with first_ctrl_c_only():
        try:
            report = restore(Config(), Path(copy))
        except RestoreRefused as refusal:
            print(f"error: {refusal}\nnothing was changed", file=sys.stderr)
            return EXIT_REFUSED
        except RestoreBroken as broken:
            print(f"error: {broken}", file=sys.stderr)
            return EXIT_HALF_RESTORED
        print(report.describe())
        return EXIT_RESTORED


@dataclass
class VerifyReport:
    """What `backup --verify` found in a copy; no ``problems`` — the copy is whole."""

    copy: Path
    created_at: str
    database: str
    storage: str
    problems: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def whole(self) -> bool:
        return not self.problems

    def describe(self) -> str:
        problems = [f"  {line}" for line in self.problems]
        verdict = ["not whole — restore refuses this copy:", *problems] if problems else ["whole"]
        return "\n".join(
            [
                f"copy:      {self.copy} (taken {self.created_at} UTC)",
                f"database:  {self.database}",
                f"storage:   {self.storage}",
                *self.notes,
                *verdict,
            ]
        )


def verify_copy(config: Config, copy: Path) -> VerifyReport:
    """The checks `restore` runs before it swaps anything in, on the copy itself, changing
    nothing; a directory that is no copy at all is `RestoreRefused`."""
    manifest = read_manifest(resolve_path(copy))
    problems: list[str] = []
    try:
        database = f"{manifest.database.name} — {_check_database(config, manifest)}"
    except BackupRefused as refusal:
        database = f"{manifest.database.name} — not usable"
        problems.append(str(refusal))

    notes = []
    if manifest.storage is None or manifest.expected is None:
        storage = "no stored files in the copy"
    elif not manifest.storage.is_dir():
        storage = "missing"
        problems.append(f"the copy of the stored files is missing: {manifest.storage}")
    else:
        found = scan_tree(manifest.storage)
        storage = f"{len(found)} file(s), {sum(found.values())} byte(s) in {STORAGE_DIR_NAME}/"
        notes.append(f"checked:   {manifest.expected.describe()}")
        problems.extend(differences(manifest.expected, found))

    if manifest.provider != config.db_provider:
        notes.append(
            f"provider:  {manifest.provider} — this install runs on {config.db_provider}, "
            "restore here refuses it"
        )
    return VerifyReport(
        copy=manifest.directory,
        created_at=manifest.created_at,
        database=database,
        storage=storage,
        problems=problems,
        notes=notes,
    )


def verify_command(copy: str) -> int:
    """`app.py backup --verify <copy>`: the report on stdout; 0 — whole, 1 — not, or no copy."""
    with first_ctrl_c_only():
        try:
            report = verify_copy(Config(), Path(copy))
        except RestoreRefused as refusal:
            print(f"error: {refusal}", file=sys.stderr)
            return EXIT_NOT_WHOLE
        except KeyboardInterrupt:
            print(f"error: {INTERRUPTED} — the copy was not checked to the end", file=sys.stderr)
            return EXIT_NOT_WHOLE
        print(report.describe())
        return EXIT_WHOLE if report.whole else EXIT_NOT_WHOLE


def _verify_copy(config: Config, manifest: Manifest) -> None:
    if manifest.provider != config.db_provider:
        raise RestoreRefused(
            f"the copy is of a {manifest.provider} base, this install runs on {config.db_provider}"
        )
    if manifest.directory.resolve().is_relative_to(config.storage_root.resolve()):
        raise RestoreRefused(
            f"the copy lies inside the storage root it would replace ({config.storage_root}): "
            "the swap would move it aside midway. Move it out first"
        )
    if manifest.storage is not None and not manifest.storage.is_dir():
        raise RestoreRefused(f"the copy of the stored files is missing: {manifest.storage}")
    try:
        _check_database(config, manifest)
    except BackupRefused as refusal:
        raise RestoreRefused(str(refusal)) from refusal


def _check_database(config: Config, manifest: Manifest) -> str:
    """The database copy by the provider that took it — the verification line, or a refusal."""
    if not manifest.database.is_file():
        raise BackupRefused(f"the database copy is missing: {manifest.database}")
    if manifest.provider == "sqlite":
        integrity, _violations = check_sqlite_file(manifest.database)
        return f"integrity_check: {integrity}"
    archived = list_postgres_archive(config, manifest.database)
    return f"pg_restore --list: ok, {archived} object(s) in the archive"


def _refuse_unless_whole(manifest: Manifest, staged: TreeSnapshot) -> str:
    """The prepared tree against what the copy recorded; answers how it was checked."""
    if manifest.expected is None:
        return "no stored files in the copy"
    found = differences(manifest.expected, staged.entries)
    if found:
        raise RestoreRefused(
            "the stored files of the copy are not what it recorded — the copy changed after it "
            "was taken:\n"
            + "\n".join(f"  {line}" for line in found)
            + f"\ncheck a copy without restoring it: uv run python src/app.py backup --verify "
            f"{manifest.directory}"
        )
    return manifest.expected.describe()


def _refuse_if_running() -> None:
    plan = plan_live_stop()
    if plan.is_empty and not plan.foreign and not plan.strays:
        return
    raise RestoreRefused(
        "the install is running — a base is not replaced under its writer. Stop it first:\n"
        "  uv run python src/app.py stop\n" + plan.describe()
    )


@dataclass
class _Swap:
    """Renames done so far, so a failure can put them back in reverse."""

    done: list[tuple[Path, Path]] = field(default_factory=list)

    def move(self, source: Path, target: Path) -> None:
        os.rename(source, target)
        self.done.append((source, target))

    def undo(self) -> None:
        while self.done:
            source, target = self.done[-1]
            os.rename(target, source)
            self.done.pop()

    def describe(self) -> list[str]:
        return [f"{source} → {target}" for source, target in self.done]


@dataclass
class _Staging:
    """What this run puts beside the install before the swap: the prepared tree, the prepared
    SQLite base or the dump of the PostgreSQL one, the folders made for them. A refusal removes
    exactly this. Each name carries the run's stamp and was free when the run began
    (`_refuse_names_taken`), and the maintenance flag keeps any other restore out — so whatever
    stands at these names afterwards is this run's own."""

    root: Path
    base: Path | None = None
    dump: Path | None = None
    folders: list[Path] = field(default_factory=list)

    def make_parents(self, path: Path) -> None:
        self.folders.extend(make_parents(path))

    def discard(self, *, keep_dump: bool = False) -> None:
        with sigint_ignored():
            remove_tree(self.root, ignore_errors=True)
            kept = (self.dump,) if keep_dump else ()
            for path in (self.base, self.dump):
                if path is not None and path not in kept:
                    with suppress(OSError):
                        path.unlink(missing_ok=True)
            remove_made(self.folders)


def _restore_stopped(config: Config, manifest: Manifest, stamp: str) -> RestoreReport:
    root = config.storage_root
    aside_root = _beside(root, ASIDE_MARK, stamp)
    staging = _Staging(root=_beside(root, STAGED_MARK, stamp))
    moved_aside: list[Path] = []
    with _interrupt_refuses("the copy was being prepared"):
        try:
            if config.db_provider == "sqlite":
                staging.base = _beside(sqlite_source(config), STAGED_MARK, stamp)
                moved_aside = _with_sidecars(_beside(sqlite_source(config), ASIDE_MARK, stamp))
            else:
                staging.dump = _dump_target(config, stamp)
        except BackupRefused as refusal:
            raise RestoreRefused(str(refusal)) from refusal
        _refuse_names_taken([staging.root, aside_root, *moved_aside, staging.base, staging.dump])

    try:
        staging.make_parents(staging.root)
        files = _stage_files(manifest, staging.root)
        checked = _refuse_unless_whole(manifest, files)
        if staging.base is not None:
            staging.make_parents(staging.base)
            _stage_sqlite(manifest, staging.base)
        elif staging.dump is not None:
            staging.make_parents(staging.dump)
            _dump_aside(config, staging.dump)
    except RestoreRefused:
        staging.discard()
        raise
    except KeyboardInterrupt:
        staging.discard()
        raise RestoreRefused(f"{INTERRUPTED} while the copy was being prepared") from None
    except (BackupRefused, OSError) as failure:
        staging.discard()
        raise RestoreRefused(f"the copy could not be prepared: {failure}") from failure

    swap = _Swap()
    reset = _Reset()
    try:
        # A few renames, done in milliseconds — but Ctrl-C landing between a rename and its
        # record would make the undo miss it, so it is held off for them.
        with sigint_ignored():
            try:
                if root.exists():
                    swap.move(root, aside_root)
                swap.move(staging.root, root)
                if staging.base is not None:
                    database = _swap_sqlite(config, staging.base, swap, stamp)
            except (OSError, KeyboardInterrupt) as failure:
                _undo_or_break(swap, f"the swap failed ({_described(failure)})", staging)
        if staging.dump is not None:
            database = _restore_postgres(config, manifest, reset)
    except (RestoreRefused, RestoreBroken):
        raise
    except (Exception, KeyboardInterrupt) as failure:  # noqa: BLE001 — judged by how far it got
        with sigint_ignored():
            database = _settle(config, swap, staging, reset, failure)

    aside: list[Path] = [target for _source, target in swap.done if ASIDE_MARK in target.name]
    if staging.dump is not None:
        aside.append(staging.dump)
    return RestoreReport(
        copy=manifest.directory,
        database=database,
        files=files,
        aside=[str(path) for path in aside],
        checked=checked,
    )


def _beside(path: Path, mark: str, stamp: str) -> Path:
    return path.with_name(f"{path.name}.{mark}.{stamp}")


def _with_sidecars(base: Path) -> list[Path]:
    return [Path(f"{base}{suffix}") for suffix in ("", *SQLITE_SIDECARS)]


def _dump_target(config: Config, stamp: str) -> Path:
    return (
        resolve_runtime_root()
        / BACKUP_FOLDER_NAME
        / f"{config.db_name}.{ASIDE_MARK}.{stamp}.dump"
    )


def _described(failure: BaseException) -> str:
    return INTERRUPTED if isinstance(failure, KeyboardInterrupt) else str(failure)


def _refuse_names_taken(names: Iterable[Path | None]) -> None:
    """What already stands at a name this run would create is not the run's to replace or
    remove: an earlier restore within the same second left it, or a hand put it there."""
    taken = [name for name in names if name is not None and os.path.lexists(name)]
    if taken:
        raise RestoreRefused(
            "this restore would create names that already exist:\n"
            + "\n".join(f"  {name}" for name in taken)
            + "\nan earlier restore within the same second left them, or a hand put them there: "
            "move them away, or wait a second for a new stamp, and run it again"
        )


def _stage_files(manifest: Manifest, staged_root: Path) -> TreeSnapshot:
    """The copy's file tree beside the storage root, linked back from the copy, which stays whole."""
    if manifest.storage is None:
        staged_root.mkdir()
        return TreeSnapshot(files=0, size=0, linked=0, copied=0)
    snapshot = snapshot_tree(manifest.storage, staged_root)
    if snapshot is None:  # pragma: no cover — verified to exist a moment ago
        raise RestoreRefused(f"the copy of the stored files is gone: {manifest.storage}")
    return snapshot


def _stage_sqlite(manifest: Manifest, staged: Path) -> None:
    """A writable copy of the database copy beside the base — the copy itself is never opened
    for writing, so restoring it twice gives the same base twice."""
    shutil.copyfile(manifest.database, staged)
    check_sqlite_file(staged)


def _swap_sqlite(config: Config, staged: Path, swap: _Swap, stamp: str) -> str:
    current = sqlite_source(config)
    aside = _beside(current, ASIDE_MARK, stamp)
    for suffix in ("", *SQLITE_SIDECARS):
        present = Path(f"{current}{suffix}")
        if present.exists():
            swap.move(present, Path(f"{aside}{suffix}"))
    swap.move(staged, current)
    return str(current)


def _undo(swap: _Swap) -> OSError | None:
    """Put the renames back; answers what stopped it, if anything did."""
    try:
        with sigint_ignored():
            swap.undo()
    except OSError as broken_undo:
        return broken_undo
    return None


def _undo_or_break(swap: _Swap, reason: str, staging: _Staging) -> NoReturn:
    """Nothing reached the base yet: the renames undone and the staging discarded, it is a
    refusal — the dump aside included, a duplicate of a base nothing changed."""
    done = swap.describe()
    broken_undo = _undo(swap)
    if broken_undo is not None:
        kept = f"\nthe base is untouched; its dump aside: {staging.dump}" if staging.dump else ""
        raise RestoreBroken(
            f"restore stopped midway: {reason}, and could not be undone ({broken_undo}).\n"
            "renamed so far:\n" + "\n".join(f"  {line}" for line in swap.describe()) + kept
        )
    staging.discard()
    raise RestoreRefused(
        f"{reason} — the swap was undone:\n" + "\n".join(f"  {line}" for line in done)
    )


def _dump_aside(config: Config, target: Path) -> None:
    try:
        dump_postgres(config, target)
    except BackupRefused as refusal:
        raise RestoreRefused(
            f"the current base could not be dumped aside before the restore: {refusal}"
        ) from refusal


@dataclass
class _Reset:
    """How far the PostgreSQL half got — what a failure anywhere past the renames is judged by.
    ``sent``: the reset went to the base; ``answered``: PostgreSQL emptied the schema;
    ``restored``: `pg_restore` put the copy in."""

    sent: bool = False
    answered: bool = False
    restored: bool = False


class _PgRestoreFailed(Exception):
    """`pg_restore` ran and answered with an error; the message is its stderr."""


def _restore_postgres(config: Config, manifest: Manifest, reset: _Reset) -> str:
    """Into an empty `public` schema. Emptying it is the one step past which the install cannot
    be put back by renaming; every failure is judged by ``reset`` (`_settle`)."""
    pg_restore = require_tool("pg_restore")
    asyncio.run(_reset_schema(config, reset))
    restored = run_tool(
        [
            pg_restore,
            "--single-transaction",
            "--exit-on-error",
            "--no-owner",
            *postgres_connection(config),
            str(manifest.database),
        ],
        postgres_environment(config),
    )
    if restored.returncode != 0:
        raise _PgRestoreFailed(restored.stderr.strip())
    reset.restored = True
    return _postgres_name(config)


def _postgres_name(config: Config) -> str:
    return f"{config.db_user}@{config.db_host}:{config.db_port}/{config.db_name}"


def _settle(
    config: Config, swap: _Swap, staging: _Staging, reset: _Reset, failure: BaseException
) -> str:
    """What a failure past the renames leaves, by how far the base got — whether Ctrl-C or an
    error, and wherever between two steps it lands. Answers the base when it is restored after
    all; otherwise raises.

    - nothing sent to the base, or PostgreSQL answered the reset with an error (the two
      statements run as one implicit transaction, rolled back on error): the renames go back —
      a refusal;
    - the reset sent and no answer back (a connection lost, Ctrl-C): the base is either as it
      was or empty, so the files go back and the dump stays — `_put_back_unsure`;
    - the schema emptied: `RestoreBroken` naming the dump, the files moved aside, the way back.
    """
    if reset.restored:
        return _postgres_name(config)
    if reset.answered:
        known = isinstance(failure, (_PgRestoreFailed, BackupRefused))
        reason = str(failure) if known else _described(failure)
        raise RestoreBroken(
            f"pg_restore failed after the schema was emptied:\n{reason}\n"
            "the stored files are already restored; what stood there is aside:\n"
            + "\n".join(f"  {line}" for line in _aside_of(swap))
            + f"\nthe previous base is in {staging.dump}.\nput both back — the base:\n"
            f"  {_restore_hint(config, staging.dump)}\n"
            "and the files: the restored root moved away, the one aside renamed into its place"
        )
    if reset.sent and not _answered_by_the_server(failure):
        _put_back_unsure(config, swap, staging, _described(failure))
    if isinstance(failure, BackupRefused):
        reason = str(failure)
    elif isinstance(failure, KeyboardInterrupt):
        reason = INTERRUPTED
    else:
        reason = f"the schema could not be emptied ({failure})"
    _undo_or_break(swap, reason, staging)


def _aside_of(swap: _Swap) -> list[str]:
    moved = [str(target) for _source, target in swap.done if ASIDE_MARK in target.name]
    return moved or ["(no stored files stood there)"]


def _put_back_unsure(config: Config, swap: _Swap, staging: _Staging, reason: str) -> NoReturn:
    """The reset was sent and no answer came back (a connection lost, Ctrl-C): the base is either
    as it was or empty. The files go back as they were, and the dump stays — if the schema was
    emptied, it is the only way back to that base."""
    broken_undo = _undo(swap)
    if broken_undo is None:
        staging.discard(keep_dump=True)
        files = "the stored files are put back as they were"
    else:
        files = f"the stored files could not be put back ({broken_undo}); renamed so far:\n" + (
            "\n".join(f"  {line}" for line in swap.describe())
        )
    raise RestoreBroken(
        f"the schema reset got no answer ({reason}) — whether PostgreSQL emptied the schema "
        f"cannot be told from here.\n{files}\n"
        f"the base as it stood before is dumped in {staging.dump}; if the base is empty now, "
        "put it back:\n"
        f"  {_restore_hint(config, staging.dump)}\n"
        "remove the dump once the base is checked"
    )


async def _reset_schema(config: Config, reset: _Reset) -> None:
    """Marks ``reset`` as the statement goes and as it is answered. Closing after the answer
    decides nothing, so its failure is not one."""
    connection = await connect_postgres(config)
    try:
        reset.sent = True
        await connection.execute(_RESET_SCHEMA)
        reset.answered = True
    finally:
        with suppress(Exception):
            await connection.close()


def _answered_by_the_server(failure: BaseException) -> bool:
    """An error PostgreSQL itself sent back. asyncpg also reports a connection it lost as a
    `PostgresConnectionError` — after which the reset may or may not have committed."""
    import asyncpg

    return isinstance(failure, asyncpg.PostgresError) and not isinstance(
        failure, asyncpg.exceptions.PostgresConnectionError
    )


def _restore_hint(config: Config, archive: Path) -> str:
    return (
        f"pg_restore --clean --if-exists --no-owner --host {config.db_host} --port "
        f"{config.db_port} --username {config.db_user} --dbname {config.db_name} {archive}"
    )


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print("usage: restore <copy directory>", file=sys.stderr)
        return EXIT_REFUSED
    return restore_command(argv[0])


__all__ = [
    "EXIT_HALF_RESTORED",
    "EXIT_NOT_WHOLE",
    "EXIT_REFUSED",
    "EXIT_RESTORED",
    "EXIT_WHOLE",
    "Manifest",
    "RestoreBroken",
    "RestoreRefused",
    "RestoreReport",
    "VerifyReport",
    "read_manifest",
    "restore",
    "restore_command",
    "verify_command",
    "verify_copy",
]


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
