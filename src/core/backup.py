"""A copy of the database and of the stored files, taken before anything is allowed to migrate it.

Shipped code on purpose. `AGENTS/` is not in git, so a tool that lives only in a developer's
checkout is absent exactly where the copy matters most: on a live install, after the merge, with
the old schema still under the new code.

**One copy is a directory**: the database copy, a snapshot of the storage root
(`Config.storage_root`) in `storage/`, the inventory of that snapshot (`inventory.json`, every
file by name and size — `src/core/backup_inventory.py`), and `backup.json`, written last — a
directory without it is not a copy, and `restore` refuses it. A base restored without its files
would hold rows whose bytes are gone; the inventory is what lets `restore` tell a whole copy from
one that lost files after it was taken.

**The database first, the files second.** A registration commits the row before it moves the
bytes into place, and the cleanup removes bytes only after the row's deletion is committed. So a
snapshot of the files taken after the database copy finds the bytes of every row that copy holds
live; bytes registered in between are extra — no row in the copy points at them — and harmless.
The reverse order would lose the bytes of every file registered between the two snapshots.

**Hard links, not copies.** Stored bytes never change in place: they are read-only and new
content always arrives through `replace`, a new inode. A link is therefore a snapshot, and a
second copy of the same files costs no space. Where a link cannot be made — the copy on another
disk, a file system without links — the file is copied. The tree is taken whole, without knowing
the storage module's tables; only half-written temporaries (`*.part`) are left out.

**SQLite.** Copying the file (`cp`) is a documented way to obtain a corrupt copy: it reads the
file linearly while a writer rewrites pages it has already passed. In WAL mode a second hazard is
added — committed data sits in the sidecar until a checkpoint, so a copy of the main file alone
silently lags. `VACUUM INTO` takes a consistent snapshot under a read transaction and lands it as
a single file with no sidecars. The copy is verified immediately: `integrity_check` must answer
`ok`. `foreign_key_check` is reported separately — reference checking is off in the application,
so its findings are diagnostics, not a failed copy.

Restoring is `app.py restore <copy>` (`src/core/restore.py`): it puts the database and the files
back together and moves the current ones aside.

The manifest says who took the copy (`made_by`): the update's own copies are the only ones its
retention may remove (`src/core/backup_retention.py`); a copy taken by hand, or one older than the
field, is never removed by anything but the operator.

**PostgreSQL.** `pg_dump --format=custom` is a snapshot under a single read transaction —
consistent on a live base and selectively restorable. Verification is `pg_restore --list`: it
parses the archive's table of contents and fails on a truncated or corrupt file, which is the
role `integrity_check` plays for SQLite. The password travels in `PGPASSWORD`, not on a command
line that the process table shows to everyone. A missing `pg_dump`/`pg_restore` is a refusal
naming `postgresql-client`, never a silent skip: an update may not migrate blind.
"""

from __future__ import annotations

import itertools
import json
import os
import shutil
import signal
import sqlite3
import subprocess
import sys
import threading
from collections.abc import Iterator, Sequence
from contextlib import closing, contextmanager, suppress
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from src.core.app_path import project_root, resolve_runtime_root
from src.core.backup_inventory import INVENTORY_NAME, PARTIAL_SUFFIX, write_inventory
from src.core.config import Config

DUMP_TIMEOUT_SECONDS = 3600
FOREIGN_KEY_VIOLATIONS_SHOWN = 10
POSTGRES_CLIENT_PACKAGE = "postgresql-client"

MANIFEST_NAME = "backup.json"
MANIFEST_FORMAT = 1
STORAGE_DIR_NAME = "storage"
BACKUP_FOLDER_NAME = "backup"
# Who took the copy decides whether the retention may ever remove it: only the update's own
# copies are counted against `UPDATE_KEEP_BACKUPS`, and a copy without the field is manual.
MADE_BY_UPDATE = "update"
MADE_BY_MANUAL = "manual"
MADE_BY_CHOICES = (MADE_BY_MANUAL, MADE_BY_UPDATE)

_ALEMBIC_HEADS = "SELECT version_num FROM alembic_version"
STAMP_FORMAT = "%Y%m%d-%H%M%S"
MANIFEST_TIMESTAMP_FORMAT = "%Y-%m-%d %H:%M:%S"


class BackupRefused(RuntimeError):
    """No copy was taken; the message is what the operator reads."""


@dataclass(frozen=True)
class TreeSnapshot:
    """What a snapshot of a folder tree holds: its files, how many were linked and how many
    copied, and what was not taken (symbolic links are never followed out of the tree).
    ``entries`` — every file taken, its path inside the tree → its size."""

    files: int
    size: int
    linked: int
    copied: int
    skipped: int = 0
    entries: dict[str, int] = field(default_factory=dict, repr=False, compare=False)

    def describe(self) -> str:
        skipped = f", {self.skipped} symbolic link(s) left out" if self.skipped else ""
        return (
            f"{self.files} file(s), {self.size / 1024 / 1024:.1f} MB "
            f"({self.linked} linked, {self.copied} copied{skipped})"
        )


@dataclass(frozen=True)
class Backup:
    """A copy that exists and has passed its verification."""

    source: str
    target: Path
    database: Path
    revisions: tuple[str, ...]
    verification: str
    storage_source: Path | None = None
    storage: TreeSnapshot | None = None
    diagnostics: tuple[str, ...] = ()
    made_by: str = MADE_BY_MANUAL

    def describe(self) -> str:
        return "\n".join(
            [
                f"source:    {self.source}",
                f"copy:      {self.target} (made by {self.made_by})",
                f"database:  {self.database.name} ({_megabytes(self.database)})",
                f"revisions: {', '.join(self.revisions) or '(none read)'}",
                f"verified:  {self.verification}",
                f"storage:   {self._storage_line()}",
                *self.diagnostics,
            ]
        )

    def _storage_line(self) -> str:
        if self.storage is None:
            return f"{self.storage_source} does not exist — no stored files to keep"
        return f"{self.storage_source} → {STORAGE_DIR_NAME}/: {self.storage.describe()}"


def backup_folder(config: Config) -> Path:
    """The folder copies land in by default: next to a file base, otherwise under the runtime
    root of this profile. The retention looks for the update's copies here and nowhere else."""
    if config.db_provider == "sqlite":
        return sqlite_source(config).parent / BACKUP_FOLDER_NAME
    return resolve_runtime_root() / BACKUP_FOLDER_NAME


def database_file_name(config: Config) -> str:
    """The name the database takes inside a copy — what the manifest's `database` says."""
    if config.db_provider == "sqlite":
        return sqlite_source(config).name
    return f"{config.db_name}.dump"


def default_target(config: Config) -> Path:
    """Where a copy lands when the caller names no path."""
    stamp = datetime.now().strftime(STAMP_FORMAT)
    stem = sqlite_source(config).name if config.db_provider == "sqlite" else config.db_name
    return backup_folder(config) / f"{stem}.{stamp}"


def back_up(
    config: Config, target: Path | None = None, *, made_by: str = MADE_BY_MANUAL
) -> Backup:
    """Take the copy — the database first, the stored files second — and verify it, or refuse.

    Never overwrites anything: the directory must not exist. A refusal leaves nothing behind.
    """
    if made_by not in MADE_BY_CHOICES:
        raise BackupRefused(f"made_by must be one of {', '.join(MADE_BY_CHOICES)}: {made_by!r}")
    storage_root = config.storage_root
    wanted = resolve_path(target if target is not None else default_target(config))
    if wanted.resolve().is_relative_to(storage_root.resolve()):
        raise BackupRefused(
            f"the copy would land inside the storage root it copies ({storage_root}): {wanted}"
        )
    directory, made = _prepare_target(wanted)
    try:
        directory.mkdir()
    except OSError as failure:
        remove_made(made)
        if isinstance(failure, FileExistsError):
            raise BackupRefused(f"already exists, refusing to overwrite it: {directory}") from None
        raise BackupRefused(f"the copy directory cannot be made: {failure}") from failure

    try:
        if config.db_provider == "sqlite":
            database = _back_up_sqlite(config, directory / database_file_name(config))
        else:
            database = dump_postgres(config, directory / database_file_name(config))
        try:
            storage = snapshot_tree(storage_root, directory / STORAGE_DIR_NAME)
        except OSError as failure:
            raise BackupRefused(f"the stored files could not be copied: {failure}") from failure
        copy = Backup(
            source=database.source,
            target=directory,
            database=database.target,
            revisions=database.revisions,
            verification=database.verification,
            storage_source=storage_root,
            storage=storage,
            diagnostics=database.diagnostics,
            made_by=made_by,
        )
        try:
            _write_manifest(config, copy)
        except OSError as failure:
            raise BackupRefused(f"the copy could not be written: {failure}") from failure
    except BaseException:
        with sigint_ignored():
            remove_tree(directory, ignore_errors=True)
            remove_made(made)
        raise
    return copy


def snapshot_tree(source: Path, target: Path) -> TreeSnapshot | None:
    """Mirror the tree at ``source`` into ``target``, which must not exist: every regular file
    hard-linked, or copied where no link can be made. ``None`` — there is no tree at ``source``.

    A file that vanishes midway — the cleanup removed it — is simply not in the snapshot: a row
    the copy still holds for it is marked deleted already. A folder that cannot be read raises
    `OSError`: skipping it would leave its files out of the snapshot and out of its inventory
    alike, and the copy would pass every check while missing them.
    """
    if not source.is_dir():
        return None
    target.mkdir()
    linked = copied = skipped = 0
    entries: dict[str, int] = {}
    for folder, _subfolders, names in os.walk(source, onerror=_unless_vanished):
        here = Path(folder)
        mirror = target / here.relative_to(source)
        mirror.mkdir(exist_ok=True)
        for name in sorted(names):
            if name.endswith(PARTIAL_SUFFIX):
                continue
            origin = here / name
            if origin.is_symlink() or not origin.is_file():
                skipped += 1
                continue
            try:
                was_linked = _link_or_copy(origin, mirror / name)
            except FileNotFoundError:
                continue
            entries[origin.relative_to(source).as_posix()] = (mirror / name).stat().st_size
            linked += was_linked
            copied += not was_linked
    return TreeSnapshot(
        files=len(entries),
        size=sum(entries.values()),
        linked=linked,
        copied=copied,
        skipped=skipped,
        entries=entries,
    )


def _unless_vanished(failure: OSError) -> None:
    """A folder gone midway held only files the cleanup removed; any other failure is raised."""
    if not isinstance(failure, FileNotFoundError):
        raise failure


def _link_or_copy(origin: Path, target: Path) -> bool:
    """``True`` — linked; ``False`` — copied, its size checked against the original."""
    try:
        os.link(origin, target)
        return True
    except FileNotFoundError:
        raise
    except OSError:
        pass
    try:
        shutil.copy2(origin, target)
        expected = origin.stat().st_size
    except FileNotFoundError:
        # The cleanup removed the original mid-copy: the bytes left behind would be a file the
        # inventory does not list, and the copy would fail its own check.
        target.unlink(missing_ok=True)
        raise
    if target.stat().st_size != expected:
        raise BackupRefused(f"the copy of {origin} is not whole: {target}")
    return False


def make_parents(path: Path) -> list[Path]:
    """Make the missing folders above ``path``; answers them topmost first, so that a refusal
    can take back exactly what it made (`remove_made`)."""
    missing = list(itertools.takewhile(lambda folder: not folder.exists(), path.parents))
    made: list[Path] = []
    try:
        for folder in reversed(missing):
            folder.mkdir()
            made.append(folder)
    except BaseException:
        remove_made(made)
        raise
    return made


def remove_made(folders: Sequence[Path]) -> None:
    """The folders `make_parents` made, deepest first; one that something filled meanwhile is
    not empty and stays."""
    for folder in reversed(folders):
        with suppress(OSError):
            folder.rmdir()


def remove_tree(root: Path, *, ignore_errors: bool = False) -> None:
    """`shutil.rmtree`, and where it gives up — it recurses once per level, so a tree nested
    past the interpreter's recursion limit raises `RecursionError` midway — the rest removed
    bottom-up by an iterative walk. Every path of a tree `snapshot_tree` made is under PATH_MAX,
    so the walk reaches all of it."""
    try:
        shutil.rmtree(root, ignore_errors=ignore_errors)
    except RecursionError:
        _remove_bottom_up(root, ignore_errors=ignore_errors)


def _remove_bottom_up(root: Path, *, ignore_errors: bool) -> None:
    def attempt(remove, path: str) -> None:
        try:
            remove(path)
        except OSError:
            if not ignore_errors:
                raise

    def walk_failed(failure: OSError) -> None:
        if not ignore_errors:
            raise failure

    for folder, subfolders, names in os.walk(root, topdown=False, onerror=walk_failed):
        for name in names:
            attempt(os.unlink, os.path.join(folder, name))
        for name in subfolders:
            path = os.path.join(folder, name)
            # A link to a folder is listed among the folders but never entered: it goes as a name.
            attempt(os.unlink if os.path.islink(path) else os.rmdir, path)
    attempt(os.rmdir, str(root))


@contextmanager
def sigint_ignored() -> Iterator[None]:
    """Ctrl-C ignored while a cleanup runs: a second press would stop it halfway and leave the
    rest behind. Only the main thread sets handlers — and only it ever sees Ctrl-C; a handler
    installed outside Python (``None``) could not be put back, so it is left alone."""
    previous = signal.getsignal(signal.SIGINT)
    if previous is None or threading.current_thread() is not threading.main_thread():
        yield
        return
    signal.signal(signal.SIGINT, signal.SIG_IGN)
    try:
        yield
    finally:
        signal.signal(signal.SIGINT, previous)


@contextmanager
def first_ctrl_c_only() -> Iterator[None]:
    """For a command's whole run: the first Ctrl-C raises `KeyboardInterrupt` as ever, every
    later one is ignored — after the first the command is on its way out, cleaning up and saying
    what it left, and an impatient second press would cut exactly that short. Once pressed, the
    process stays deaf to it to the end: a press during its exit would kill it with SIGINT and
    replace the exit code the command chose."""
    previous = signal.getsignal(signal.SIGINT)
    if previous is None or threading.current_thread() is not threading.main_thread():
        yield
        return
    pressed = False

    def first_only(signum, frame) -> None:
        nonlocal pressed
        if not pressed:
            pressed = True
            raise KeyboardInterrupt

    signal.signal(signal.SIGINT, first_only)
    try:
        yield
    finally:
        signal.signal(signal.SIGINT, signal.SIG_IGN if pressed else previous)


@contextmanager
def sigint_deferred() -> Iterator[None]:
    """Ctrl-C held until a step that must not stop halfway is done, then delivered to whatever
    handler stood before — the step ends whole, and the press is not lost."""
    previous = signal.getsignal(signal.SIGINT)
    if previous is None or threading.current_thread() is not threading.main_thread():
        yield
        return
    pressed = False

    def remember(signum, frame) -> None:
        nonlocal pressed
        pressed = True

    signal.signal(signal.SIGINT, remember)
    try:
        yield
    finally:
        signal.signal(signal.SIGINT, previous)
        if pressed:
            signal.raise_signal(signal.SIGINT)


def _write_manifest(config: Config, copy: Backup) -> None:
    """The last file of a copy — its presence is what says the copy is whole. The inventory goes
    in just before it, and the manifest records its sha256: what vouches for the inventory."""
    storage = None
    if copy.storage is not None:
        storage = {
            "source": str(copy.storage_source),
            "files": copy.storage.files,
            "bytes": copy.storage.size,
            "inventory": INVENTORY_NAME,
            "inventory_sha256": write_inventory(copy.target, copy.storage.entries),
        }
    manifest = {
        "format": MANIFEST_FORMAT,
        "created_at": datetime.now(timezone.utc).strftime(MANIFEST_TIMESTAMP_FORMAT),
        "made_by": copy.made_by,
        "provider": config.db_provider,
        "database": copy.database.name,
        "revisions": list(copy.revisions),
        "storage": storage,
    }
    (copy.target / MANIFEST_NAME).write_text(json.dumps(manifest, indent=2), encoding="utf-8")


def sqlite_source(config: Config) -> Path:
    """The file the APP opens — resolved by `Config`, runtime root and all, so that a copy can
    never be of a base nobody serves."""
    source = config.sqlite_file
    if source is None:
        raise BackupRefused("DB_PATH=:memory: — there is nothing on disk to copy")
    return source


def backup_command(target: str | None = None, *, made_by: str = MADE_BY_MANUAL) -> int:
    """`app.py backup [path]`: the report on stdout, a refusal on stderr and exit 1."""
    with first_ctrl_c_only():
        try:
            backup = back_up(Config(), Path(target) if target else None, made_by=made_by)
        except BackupRefused as refusal:
            print(f"error: {refusal}", file=sys.stderr)
            return 1
        except KeyboardInterrupt:
            print("error: interrupted (Ctrl-C) — no copy was taken", file=sys.stderr)
            return 1
        print(backup.describe())
        return 0


def main(argv: Sequence[str]) -> int:
    return backup_command(argv[0] if argv else None)


def resolve_path(path: Path) -> Path:
    """A path as the operator gave it; a relative one is taken from the project root, where
    `update.sh` runs every command."""
    resolved = path.expanduser()
    return resolved if resolved.is_absolute() else project_root() / resolved


def _prepare_target(target: Path) -> tuple[Path, list[Path]]:
    """The copy's directory, and the folders above it made for it."""
    resolved = resolve_path(target)
    if resolved.exists():
        raise BackupRefused(f"already exists, refusing to overwrite it: {resolved}")
    try:
        return resolved, make_parents(resolved)
    except OSError as failure:
        raise BackupRefused(f"the folder for the copy cannot be made: {failure}") from failure


@dataclass(frozen=True)
class DatabaseCopy:
    """The database half of a copy, verified."""

    source: str
    target: Path
    revisions: tuple[str, ...]
    verification: str
    diagnostics: tuple[str, ...] = ()


def _back_up_sqlite(config: Config, target: Path) -> DatabaseCopy:
    source = sqlite_source(config)
    if not source.exists():
        raise BackupRefused(f"database file not found: {source}")

    try:
        with closing(sqlite3.connect(read_only_uri(source), uri=True)) as base:
            revisions = _sqlite_revisions(base)
            base.execute("VACUUM INTO ?", (str(target),))
    except sqlite3.Error as failure:
        raise BackupRefused(f"the base could not be copied ({failure}): {source}") from failure
    integrity, violations = check_sqlite_file(target)
    return DatabaseCopy(
        source=f"{source} ({_megabytes(source)})",
        target=target,
        revisions=revisions,
        verification=f"integrity_check: {integrity}",
        diagnostics=_foreign_key_report(violations),
    )


def check_sqlite_file(path: Path) -> tuple[str, list[tuple]]:
    """``integrity_check`` must answer ``ok``, or the file is no copy; the foreign-key findings
    come back as diagnostics — reference checking is off in the application."""
    try:
        with closing(sqlite3.connect(read_only_uri(path), uri=True)) as copy:
            integrity = copy.execute("PRAGMA integrity_check").fetchone()[0]
            violations = copy.execute("PRAGMA foreign_key_check").fetchall()
    except sqlite3.DatabaseError as failure:
        raise BackupRefused(f"not a readable SQLite database ({failure}): {path}") from failure
    if integrity != "ok":
        raise BackupRefused(f"the copy failed its integrity check ({integrity}): {path}")
    return integrity, violations


def read_only_uri(path: Path) -> str:
    """The base opened read-only through a URI, its path percent-encoded: raw, a `#` or `?` in a
    folder name would cut the path short — SQLite would check another file, or create an empty
    one where the cut fell."""
    return f"{path.absolute().as_uri()}?mode=ro"


def _sqlite_revisions(connection: sqlite3.Connection) -> tuple[str, ...]:
    """Alembic heads as of the copy — one per branch (core + modules)."""
    try:
        rows = connection.execute(_ALEMBIC_HEADS).fetchall()
    except sqlite3.DatabaseError:
        return ()
    return tuple(sorted(row[0] for row in rows))


def _foreign_key_report(violations: Sequence[tuple]) -> tuple[str, ...]:
    if not violations:
        return ("foreign_key_check: no violations",)
    listed = [
        f"  {child_table} rowid={rowid} → {parent_table} (constraint #{ordinal})"
        for child_table, rowid, parent_table, ordinal in violations[:FOREIGN_KEY_VIOLATIONS_SHOWN]
    ]
    hidden = len(violations) - FOREIGN_KEY_VIOLATIONS_SHOWN
    tail = [f"  … and {hidden} more"] if hidden > 0 else []
    return (f"foreign_key_check: {len(violations)} violation(s)", *listed, *tail)


def dump_postgres(config: Config, target: Path) -> DatabaseCopy:
    """`pg_dump --format=custom` of the configured base into ``target``, verified."""
    pg_dump = require_tool("pg_dump")
    require_tool("pg_restore")
    revisions = _postgres_revisions(config)
    environment = postgres_environment(config)

    dump = run_tool(
        [pg_dump, *postgres_connection(config), "--format=custom", "--file", str(target)],
        environment,
    )
    if dump.returncode != 0:
        target.unlink(missing_ok=True)
        raise BackupRefused(f"pg_dump failed:\n{dump.stderr.strip()}")

    try:
        archived = list_postgres_archive(config, target)
    except BackupRefused:
        target.unlink(missing_ok=True)
        raise
    return DatabaseCopy(
        source=f"{config.db_user}@{config.db_host}:{config.db_port}/{config.db_name}",
        target=target,
        revisions=revisions,
        verification=f"pg_restore --list: ok, {archived} object(s) in the archive",
    )


def list_postgres_archive(config: Config, archive: Path) -> int:
    """`pg_restore --list` reads the archive's table of contents and fails on a truncated or
    corrupt file — the role `integrity_check` plays for SQLite. Answers how many objects it
    holds."""
    listing = run_tool(
        [require_tool("pg_restore"), "--list", str(archive)], postgres_environment(config)
    )
    if listing.returncode != 0:
        raise BackupRefused(f"pg_restore cannot read {archive}:\n{listing.stderr.strip()}")
    return sum(1 for line in listing.stdout.splitlines() if line and not line.startswith(";"))


def require_tool(name: str) -> str:
    found = shutil.which(name)
    if found is None:
        raise BackupRefused(
            f"{name} is not in PATH — install {POSTGRES_CLIENT_PACKAGE} "
            f"(no older than the server, or {name} refuses to run at all)"
        )
    return found


def postgres_connection(config: Config) -> list[str]:
    return [
        "--host", config.db_host,
        "--port", str(config.db_port),
        "--username", config.db_user,
        "--dbname", config.db_name,
    ]


def postgres_environment(config: Config) -> dict[str, str]:
    environment = dict(os.environ)
    if config.db_password:
        environment["PGPASSWORD"] = config.db_password
    return environment


async def connect_postgres(config: Config):
    """An asyncpg connection to the configured base, outside the application's engine."""
    import asyncpg

    return await asyncpg.connect(
        host=config.db_host,
        port=config.db_port,
        user=config.db_user,
        password=config.db_password or None,
        database=config.db_name,
        ssl=config.db_connect_args.get("ssl"),
        timeout=config.db_connect_timeout,
    )


def _postgres_revisions(config: Config) -> tuple[str, ...]:
    """Alembic heads through asyncpg — the same answer the SQLite branch reads from the file.

    Diagnostics only: a base that will not tell its revisions is still worth copying, so every
    failure here degrades to «none read» instead of refusing the copy.
    """
    import asyncio

    async def read() -> tuple[str, ...]:
        connection = await connect_postgres(config)
        try:
            rows = await connection.fetch(_ALEMBIC_HEADS)
        finally:
            await connection.close()
        return tuple(sorted(row["version_num"] for row in rows))

    try:
        return asyncio.run(read())
    except Exception:  # noqa: BLE001
        return ()


def run_tool(argv: list[str], environment: dict[str, str]) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            argv,
            env=environment,
            capture_output=True,
            text=True,
            timeout=DUMP_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.SubprocessError) as failure:
        raise BackupRefused(f"`{' '.join(argv)}` could not run: {failure}") from failure


def _megabytes(path: Path) -> str:
    return f"{path.stat().st_size / 1024 / 1024:.1f} MB"


__all__ = [
    "MADE_BY_CHOICES",
    "MADE_BY_MANUAL",
    "MADE_BY_UPDATE",
    "MANIFEST_NAME",
    "MANIFEST_TIMESTAMP_FORMAT",
    "STORAGE_DIR_NAME",
    "Backup",
    "BackupRefused",
    "DatabaseCopy",
    "TreeSnapshot",
    "back_up",
    "backup_command",
    "backup_folder",
    "check_sqlite_file",
    "database_file_name",
    "default_target",
    "dump_postgres",
    "first_ctrl_c_only",
    "list_postgres_archive",
    "main",
    "make_parents",
    "remove_made",
    "read_only_uri",
    "remove_tree",
    "sigint_deferred",
    "sigint_ignored",
    "snapshot_tree",
    "sqlite_source",
]


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
