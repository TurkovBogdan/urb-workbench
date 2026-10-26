"""`app.py backup --prune`: the update's copies past `UPDATE_KEEP_BACKUPS` removed — and nothing
else, ever.

Every update leaves a copy behind (`src/core/update/sequence.py`, step 6), and a copy holds hard
links to every stored file of its moment: the bytes the storage cleanup removed are freed only
once no copy links them any more. So the update ends by removing its own old copies, keeping the
newest N. Removing a copy is a plain `rmtree`: a link is a name, and the bytes go only with the
last name of the inode — another copy or the live storage keeps what it still links.

What may go is narrow on purpose, because a wrong removal is the one thing that cannot be undone:

- only a direct subfolder of the backup folder (`backup.backup_folder`), never a symbolic link
  and never anything that resolves elsewhere;
- only with a readable `backup.json` of the known format — a folder without one is a copy cut
  short, or something that is not a copy at all; a manifest that is no regular file or nests past
  the parser is unreadable too, never a reason to stop the rest;
- only `made_by: update` — a copy taken by hand, or one older than the field, is the operator's;
- only a copy of this install's database (`provider` and `database` match);
- never the copy the caller names as spared — the one the update has just taken.

A copy goes manifest first, folder second: an `rmtree` that stops midway then leaves a folder that
is no longer a copy — `restore` refuses it — rather than a copy with part of its files, which
would restore rows without their bytes. Ctrl-C waits until the copy at hand is gone whole, then
stops the prune; the ones after it are not touched.

A prune holds the maintenance flag while it removes, the way `restore` holds it while it links a
copy's files back: the two never run at once.
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from src.core import maintenance
from src.core.backup import (
    MADE_BY_MANUAL,
    MADE_BY_UPDATE,
    MANIFEST_FORMAT,
    MANIFEST_NAME,
    MANIFEST_TIMESTAMP_FORMAT,
    BackupRefused,
    backup_folder,
    database_file_name,
    first_ctrl_c_only,
    remove_tree,
    resolve_path,
    sigint_deferred,
    sigint_ignored,
)
from src.core.backup_inventory import read_regular_file
from src.core.config import Config
from src.core.maintenance import MaintenanceHeld

EXIT_PRUNED = 0
EXIT_PRUNE_FAILED = 1

KEEP_ALL = 0
INTERRUPTED = "interrupted (Ctrl-C)"


class PruneRefused(RuntimeError):
    """Nothing was removed; the message is what the operator reads."""


@dataclass(frozen=True)
class UpdateCopy:
    path: Path
    created_at: datetime

    def describe(self) -> str:
        return f"{self.path} (taken {self.created_at.strftime(MANIFEST_TIMESTAMP_FORMAT)} UTC)"


@dataclass(frozen=True)
class LeftAlone:
    path: Path
    reason: str

    def describe(self) -> str:
        return f"{self.path} — {self.reason}"


@dataclass(frozen=True)
class PrunePlan:
    """What the retention would do with the backup folder, decided before anything moves."""

    folder: Path
    keep: int
    kept: tuple[UpdateCopy, ...] = ()
    removed: tuple[UpdateCopy, ...] = ()
    left_alone: tuple[LeftAlone, ...] = ()

    def describe(self, *, dry_run: bool = False) -> str:
        verb = "would remove" if dry_run else "removing"
        limit = (
            "every copy is kept (UPDATE_KEEP_BACKUPS=0)"
            if self.keep == KEEP_ALL
            else f"keeping the newest {self.keep} copies taken by the update"
        )
        lines = [f"backup folder: {self.folder} — {limit}"]
        lines += [f"  {verb}: {copy.describe()}" for copy in self.removed]
        lines += [f"  keeping: {copy.describe()}" for copy in self.kept]
        lines += [f"  left alone: {entry.describe()}" for entry in self.left_alone]
        if not (self.removed or self.kept or self.left_alone):
            lines.append("  (empty)")
        return "\n".join(lines)


@dataclass
class PruneOutcome:
    removed: list[Path] = field(default_factory=list)
    failures: list[str] = field(default_factory=list)
    interrupted: bool = False


def plan_prune(config: Config, *, keep: int, spare: Path | None = None) -> PrunePlan:
    """Sort the backup folder into the update's copies to keep, those to remove, and everything
    the retention has no right to touch."""
    if keep < 0:
        raise PruneRefused(f"UPDATE_KEEP_BACKUPS={keep} is not a count of copies to keep")
    folder = backup_folder(config)
    if not folder.is_dir():
        return PrunePlan(folder=folder, keep=keep)
    root = folder.resolve()
    spared = resolve_path(spare).resolve() if spare is not None else None

    copies: list[UpdateCopy] = []
    left_alone: list[LeftAlone] = []
    for entry in sorted(folder.iterdir()):
        verdict = _classify(entry, root, config)
        if isinstance(verdict, LeftAlone):
            left_alone.append(verdict)
        else:
            copies.append(verdict)

    newest_first = sorted(copies, key=lambda copy: (copy.created_at, copy.path.name), reverse=True)
    if keep == KEEP_ALL:
        kept, removed = newest_first, []
    else:
        kept, removed = newest_first[:keep], newest_first[keep:]
    rescued = [copy for copy in removed if copy.path.resolve() == spared]
    return PrunePlan(
        folder=folder,
        keep=keep,
        kept=tuple([*kept, *rescued]),
        removed=tuple(copy for copy in removed if copy not in rescued),
        left_alone=tuple(left_alone),
    )


def prune(plan: PrunePlan) -> PruneOutcome:
    """Remove what the plan names; a copy that will not go does not stop the others. Ctrl-C does,
    once the copy at hand is gone whole — a half-removed one the retention never touches again —
    and the ones after it are not touched."""
    outcome = PruneOutcome()
    root = plan.folder.resolve()
    for copy in plan.removed:
        try:
            with sigint_deferred():
                _remove_copy(copy.path, root)
        except (OSError, PruneRefused) as failure:
            outcome.failures.append(_describe_failure(copy.path, failure))
            continue
        except KeyboardInterrupt:
            outcome.interrupted = True
            if copy.path.exists():
                outcome.failures.append(_describe_failure(copy.path, INTERRUPTED))
            else:
                outcome.removed.append(copy.path)
            break
        outcome.removed.append(copy.path)
    return outcome


def prune_command(*, dry_run: bool = False, spare: str | None = None) -> int:
    """`app.py backup --prune [--dry-run] [--spare PATH]`: the plan on stdout, every failure on
    stderr; exit 1 if anything that should have gone is still there.

    A real prune holds the maintenance flag: `restore` takes the same flag, and a copy removed
    while a restore links its files would come back with files missing — a vanished file is
    simply not in a snapshot. The update prunes after it has lowered its own flag."""
    config = Config()
    spared = Path(spare) if spare else None
    with first_ctrl_c_only():
        if dry_run:
            return _plan_and_prune(config, spared, dry_run=True)
        try:
            maintenance.begin("prune the update's old copies")
        except MaintenanceHeld as held:
            print(
                f"error: {held} — a restore or an update is at work\nnothing was removed",
                file=sys.stderr,
            )
            return EXIT_PRUNE_FAILED
        except OSError as failure:
            maintenance.end()
            print(
                f"error: the maintenance flag cannot be raised: {failure}\nnothing was removed",
                file=sys.stderr,
            )
            return EXIT_PRUNE_FAILED
        try:
            return _plan_and_prune(config, spared, dry_run=False)
        finally:
            with sigint_ignored():
                maintenance.end()


def _plan_and_prune(config: Config, spared: Path | None, *, dry_run: bool) -> int:
    try:
        plan = plan_prune(config, keep=config.update_keep_backups, spare=spared)
        print(plan.describe(dry_run=dry_run))
    except (PruneRefused, BackupRefused) as refusal:
        print(f"error: {refusal}\nnothing was removed", file=sys.stderr)
        return EXIT_PRUNE_FAILED
    except OSError as failure:
        print(
            f"error: the backup folder cannot be read: {failure}\nnothing was removed",
            file=sys.stderr,
        )
        return EXIT_PRUNE_FAILED
    except KeyboardInterrupt:
        print(f"error: {INTERRUPTED}\nnothing was removed", file=sys.stderr)
        return EXIT_PRUNE_FAILED
    if dry_run:
        return EXIT_PRUNED
    outcome = prune(plan)
    for failure in outcome.failures:
        print(f"error: {failure}", file=sys.stderr)
    if outcome.interrupted:
        print(f"error: {INTERRUPTED} — the copies after it were not touched", file=sys.stderr)
    return EXIT_PRUNE_FAILED if outcome.failures or outcome.interrupted else EXIT_PRUNED


def _classify(entry: Path, root: Path, config: Config) -> UpdateCopy | LeftAlone:
    if entry.is_symlink():
        return LeftAlone(entry, "a symbolic link, never followed")
    if not entry.is_dir():
        return LeftAlone(entry, "not a copy directory")
    if entry.resolve().parent != root:
        return LeftAlone(entry, f"resolves outside {root}")
    try:
        payload = json.loads(read_regular_file(entry / MANIFEST_NAME))
    except FileNotFoundError:
        return LeftAlone(entry, f"no {MANIFEST_NAME} — not a whole copy")
    except (OSError, ValueError, RecursionError) as failure:
        return LeftAlone(entry, f"{MANIFEST_NAME} cannot be read ({failure})")
    if not isinstance(payload, dict) or payload.get("format") != MANIFEST_FORMAT:
        return LeftAlone(entry, f"{MANIFEST_NAME} of a format this command does not know")
    if "made_by" not in payload:
        return LeftAlone(entry, f"no made_by — taken before the field, counted as {MADE_BY_MANUAL}")
    if payload["made_by"] != MADE_BY_UPDATE:
        return LeftAlone(entry, f"taken by hand (made_by: {payload['made_by']})")
    database = (payload.get("provider"), payload.get("database"))
    expected = (config.db_provider, database_file_name(config))
    if database != expected:
        return LeftAlone(entry, f"a copy of another database ({database[0]}, {database[1]})")
    try:
        created_at = datetime.strptime(str(payload.get("created_at")), MANIFEST_TIMESTAMP_FORMAT)
    except ValueError:
        return LeftAlone(entry, f"created_at in {MANIFEST_NAME} cannot be read")
    return UpdateCopy(entry, created_at)


def _remove_copy(path: Path, root: Path) -> None:
    """Checked again right before the removal: the folder is not ours alone between the plan
    and this moment."""
    if path.is_symlink() or path.resolve().parent != root:
        raise PruneRefused("it no longer sits in the backup folder as a plain directory")
    (path / MANIFEST_NAME).unlink()
    remove_tree(path)


def _describe_failure(path: Path, failure: Exception | str) -> str:
    if not path.exists():
        return f"{path} vanished before it could be removed: {failure}"
    if (path / MANIFEST_NAME).exists():
        return f"{path} was not removed and is still a whole copy: {failure}"
    return (
        f"{path} is half-removed and no longer a copy ({MANIFEST_NAME} is gone, so `restore` "
        f"refuses it and the retention never touches it again) — remove it by hand: {failure}"
    )


__all__ = [
    "EXIT_PRUNED",
    "EXIT_PRUNE_FAILED",
    "LeftAlone",
    "PruneOutcome",
    "PrunePlan",
    "PruneRefused",
    "UpdateCopy",
    "plan_prune",
    "prune",
    "prune_command",
]
