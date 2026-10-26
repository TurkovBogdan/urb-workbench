"""core/backup_retention: the update's old copies go, everything else stays — on real folders.

Every test builds its backup folder in a temp directory: copies with a manifest as `backup` writes
it, plus everything the retention must never touch — copies taken by hand, copies without the
field, folders without a manifest, files of the old format, symbolic links out of the folder.
"""

from __future__ import annotations

import json
import os
import shutil
import signal
import sqlite3
import threading
from pathlib import Path

import pytest

from src.core import backup_retention, maintenance
from src.core.backup import MANIFEST_NAME, back_up
from src.core.backup_retention import (
    EXIT_PRUNE_FAILED,
    EXIT_PRUNED,
    PruneRefused,
    plan_prune,
    prune,
    prune_command,
)
from src.core.config import Config
from tests.core.test_backup import deadline, nested

pytestmark = pytest.mark.pure

DATABASE = "app.sqlite3"


def install(tmp_path: Path) -> Config:
    return Config(
        db_provider="sqlite",
        db_path=str(tmp_path / DATABASE),
        storage_path=str(tmp_path / "storage"),
    )


def folder_of(tmp_path: Path) -> Path:
    return tmp_path / "backup"


def a_copy(
    tmp_path: Path,
    name: str,
    *,
    created_at: str,
    made_by: str | None = "update",
    **manifest_over,
) -> Path:
    """A copy as `backup` leaves it: the database, `storage/`, and the manifest."""
    directory = folder_of(tmp_path) / name
    (directory / "storage" / "public").mkdir(parents=True)
    (directory / DATABASE).write_bytes(b"database")
    (directory / "storage" / "public" / "FILE.txt").write_bytes(b"bytes")
    manifest = {
        "format": 1,
        "created_at": created_at,
        "provider": "sqlite",
        "database": DATABASE,
        "revisions": [],
        "storage": {"source": str(tmp_path / "storage"), "files": 1, "bytes": 5},
    }
    if made_by is not None:
        manifest["made_by"] = made_by
    manifest.update(manifest_over)
    (directory / MANIFEST_NAME).write_text(json.dumps(manifest), encoding="utf-8")
    return directory


def update_copies(tmp_path: Path, count: int) -> list[Path]:
    """Oldest first, one a day."""
    return [
        a_copy(
            tmp_path,
            f"{DATABASE}.202610{day:02d}-120000",
            created_at=f"2026-10-{day:02d} 12:00:00",
        )
        for day in range(1, count + 1)
    ]


def names(paths) -> list[str]:
    return sorted(Path(getattr(path, "path", path)).name for path in paths)


# ── the count ────────────────────────────────────────────────────────────────

def test_keeps_the_newest_copies_of_the_update_and_removes_the_rest(tmp_path: Path):
    copies = update_copies(tmp_path, 5)

    plan = plan_prune(install(tmp_path), keep=3)
    outcome = prune(plan)

    assert names(plan.removed) == names(copies[:2])
    assert names(plan.kept) == names(copies[2:])
    assert outcome.failures == []
    assert [path.exists() for path in copies] == [False, False, True, True, True]


def test_the_order_is_the_manifest_s_timestamp_not_the_folder_name(tmp_path: Path):
    """A copy renamed by hand keeps its place: the moment it was taken is in the manifest."""
    older = a_copy(tmp_path, "zzz-renamed", created_at="2026-10-01 12:00:00")
    newer = a_copy(tmp_path, "aaa-renamed", created_at="2026-10-02 12:00:00")

    plan = plan_prune(install(tmp_path), keep=1)

    assert names(plan.removed) == [older.name]
    assert names(plan.kept) == [newer.name]


def test_zero_keeps_every_copy(tmp_path: Path):
    copies = update_copies(tmp_path, 4)

    plan = plan_prune(install(tmp_path), keep=0)
    prune(plan)

    assert plan.removed == ()
    assert all(path.exists() for path in copies)
    assert "every copy is kept" in plan.describe()


def test_the_newest_copy_always_stays(tmp_path: Path):
    copies = update_copies(tmp_path, 3)

    prune(plan_prune(install(tmp_path), keep=1))

    assert [path.exists() for path in copies] == [False, False, True]


def test_the_spared_copy_stays_whatever_its_timestamp_says(tmp_path: Path):
    """The update names the copy it has just taken: a clock set back must not cost it."""
    copies = update_copies(tmp_path, 3)
    just_taken = copies[0]

    plan = plan_prune(install(tmp_path), keep=1, spare=just_taken)
    prune(plan)

    assert just_taken.exists()
    assert copies[2].exists()
    assert not copies[1].exists()


def test_a_negative_count_is_refused_and_removes_nothing(tmp_path: Path):
    copies = update_copies(tmp_path, 2)

    with pytest.raises(PruneRefused):
        plan_prune(install(tmp_path), keep=-1)

    assert all(path.exists() for path in copies)


def test_no_backup_folder_is_nothing_to_prune(tmp_path: Path):
    plan = plan_prune(install(tmp_path), keep=1)

    assert (plan.removed, plan.kept, plan.left_alone) == ((), (), ())


# ── what is never touched ────────────────────────────────────────────────────

def test_copies_taken_by_hand_are_never_removed(tmp_path: Path):
    manual = a_copy(tmp_path, "manual-old", created_at="2026-01-01 00:00:00", made_by="manual")
    unmarked = a_copy(tmp_path, "before-the-field", created_at="2026-01-02 00:00:00", made_by=None)
    update_copies(tmp_path, 3)

    plan = plan_prune(install(tmp_path), keep=1)
    prune(plan)

    assert manual.exists() and unmarked.exists()
    reasons = {entry.path.name: entry.reason for entry in plan.left_alone}
    assert reasons["manual-old"] == "taken by hand (made_by: manual)"
    assert reasons["before-the-field"] == "no made_by — taken before the field, counted as manual"


def test_what_is_not_a_whole_copy_of_this_install_is_left_alone(tmp_path: Path):
    update_copies(tmp_path, 2)
    folder = folder_of(tmp_path)
    cut_short = folder / "cut-short"
    (cut_short / "storage").mkdir(parents=True)
    broken = a_copy(tmp_path, "broken-manifest", created_at="2026-01-01 00:00:00")
    (broken / MANIFEST_NAME).write_text("{not json", encoding="utf-8")
    future = a_copy(tmp_path, "future-format", created_at="2026-01-01 00:00:00", format=2)
    undated = a_copy(tmp_path, "undated", created_at="yesterday")
    foreign = a_copy(tmp_path, "other-base", created_at="2026-01-01 00:00:00", database="x.sqlite3")
    old_format = folder / "pre_tsm_008.sqlite3"
    old_format.write_bytes(b"a copy of the old format")

    plan = plan_prune(install(tmp_path), keep=1)
    prune(plan)

    for path in (cut_short, broken, future, undated, foreign, old_format):
        assert path.exists(), path
    assert names(plan.left_alone) == names(
        [cut_short, broken, future, undated, foreign, old_format]
    )
    assert len(plan.removed) == 1


def test_a_manifest_nested_past_the_parser_is_left_alone(tmp_path: Path):
    """One odd folder must not stop the update's retention for every other copy."""
    copies = update_copies(tmp_path, 3)
    odd = a_copy(tmp_path, "nested", created_at="2026-01-01 00:00:00")
    (odd / MANIFEST_NAME).write_text("[" * 100_000, encoding="utf-8")

    plan = plan_prune(install(tmp_path), keep=1)
    prune(plan)

    assert {entry.path.name: entry.reason for entry in plan.left_alone}["nested"].startswith(
        f"{MANIFEST_NAME} cannot be read"
    )
    assert odd.exists()
    assert [path.exists() for path in copies] == [False, False, True]


@pytest.mark.skipif(
    threading.current_thread() is not threading.main_thread(),
    reason="signal handlers belong to the main thread",
)
def test_a_manifest_that_is_no_regular_file_is_left_alone_not_waited_on(tmp_path: Path):
    """A FIFO under the manifest's name would hold the update's last step forever."""
    update_copies(tmp_path, 2)
    odd = a_copy(tmp_path, "fifo", created_at="2026-01-01 00:00:00")
    (odd / MANIFEST_NAME).unlink()
    os.mkfifo(odd / MANIFEST_NAME)

    with deadline():
        plan = plan_prune(install(tmp_path), keep=1)

    reason = {entry.path.name: entry.reason for entry in plan.left_alone}["fifo"]
    assert reason.startswith(f"{MANIFEST_NAME} cannot be read")
    assert "not a regular file" in reason


def test_a_symbolic_link_out_of_the_folder_is_never_followed(tmp_path: Path):
    """Even when what it points at looks exactly like an old copy of the update."""
    update_copies(tmp_path, 2)
    elsewhere = tmp_path / "elsewhere"
    outside = a_copy(tmp_path, "outside", created_at="2026-01-01 00:00:00")
    outside.rename(elsewhere)
    link = folder_of(tmp_path) / "app.sqlite3.20260101-000000"
    link.symlink_to(elsewhere, target_is_directory=True)

    plan = plan_prune(install(tmp_path), keep=1)
    prune(plan)

    assert (elsewhere / MANIFEST_NAME).exists()
    assert (elsewhere / "storage" / "public" / "FILE.txt").read_bytes() == b"bytes"
    assert link.is_symlink()
    assert {entry.path.name: entry.reason for entry in plan.left_alone}[link.name] == (
        "a symbolic link, never followed"
    )


def test_a_link_inside_a_removed_copy_does_not_take_its_target_along(tmp_path: Path):
    old, _newest = update_copies(tmp_path, 2)
    precious = tmp_path / "precious"
    precious.mkdir()
    (precious / "keep.txt").write_bytes(b"keep")
    (old / "storage" / "escape").symlink_to(precious, target_is_directory=True)

    prune(plan_prune(install(tmp_path), keep=1))

    assert not old.exists()
    assert (precious / "keep.txt").read_bytes() == b"keep"


def test_a_copy_swapped_for_a_link_after_the_plan_is_refused(tmp_path: Path):
    """The folder is not ours alone between the plan and the removal."""
    old, _newest = update_copies(tmp_path, 2)
    plan = plan_prune(install(tmp_path), keep=1)
    elsewhere = tmp_path / "elsewhere"
    old.rename(elsewhere)
    old.symlink_to(elsewhere, target_is_directory=True)

    outcome = prune(plan)

    assert outcome.removed == []
    assert len(outcome.failures) == 1
    assert (elsewhere / MANIFEST_NAME).exists()


# ── removal and its failures ─────────────────────────────────────────────────

def test_removing_a_copy_frees_only_what_nothing_else_links(tmp_path: Path):
    """A stored file linked by the live storage and two copies: removing one copy leaves the file
    whole in the others — `rmtree` drops a name, the bytes go with the last one."""
    live = tmp_path / "storage" / "public"
    live.mkdir(parents=True)
    (live / "FILE.txt").write_bytes(b"live bytes")
    old, newest = update_copies(tmp_path, 2)
    for copy in (old, newest):
        linked = copy / "storage" / "public" / "FILE.txt"
        linked.unlink()
        os.link(live / "FILE.txt", linked)
    assert (live / "FILE.txt").stat().st_nlink == 3

    prune(plan_prune(install(tmp_path), keep=1))

    assert not old.exists()
    assert (live / "FILE.txt").stat().st_nlink == 2
    assert (newest / "storage" / "public" / "FILE.txt").read_bytes() == b"live bytes"


def test_a_removal_that_fails_unmakes_the_copy_first_and_spares_the_others(
    tmp_path: Path, monkeypatch
):
    """The manifest goes first: a half-removed folder is no copy that `restore` would accept."""
    copies = update_copies(tmp_path, 4)
    real_rmtree = shutil.rmtree

    def disk_trouble(path, *args, **kwargs):
        if Path(path) == copies[0]:
            raise OSError(5, "Input/output error")
        return real_rmtree(path, *args, **kwargs)

    monkeypatch.setattr(shutil, "rmtree", disk_trouble)

    outcome = prune(plan_prune(install(tmp_path), keep=1))

    assert outcome.removed == [copies[2], copies[1]]
    assert copies[0].exists() and not (copies[0] / MANIFEST_NAME).exists()
    assert "half-removed and no longer a copy" in outcome.failures[0]
    assert copies[3].exists()


def test_a_copy_nested_past_the_recursion_limit_is_removed_whole(tmp_path: Path, nested):
    old, newest = update_copies(tmp_path, 2)
    (nested(old / "storage" / "public") / "DEEP.txt").write_bytes(b"deep")

    outcome = prune(plan_prune(install(tmp_path), keep=1))

    assert outcome.failures == []
    assert not old.exists()
    assert newest.exists()


def test_a_real_copy_of_the_update_is_pruned_and_a_real_manual_one_is_not(tmp_path: Path):
    """The manifest `backup` writes is the one the retention reads."""
    config = install(tmp_path)
    connection = sqlite3.connect(tmp_path / DATABASE)
    connection.execute("CREATE TABLE note (code TEXT)")
    connection.close()
    folder = folder_of(tmp_path)
    manual = back_up(config, folder / f"{DATABASE}.20261024-000000").target
    taken = [
        back_up(config, folder / f"{DATABASE}.20261025-00000{index}", made_by="update").target
        for index in range(3)
    ]

    prune(plan_prune(config, keep=2))

    assert manual.exists()
    assert [path.exists() for path in taken] == [False, True, True]


# ── the command ──────────────────────────────────────────────────────────────

def command_env(tmp_path: Path, monkeypatch, keep: str) -> None:
    """The command takes the real maintenance flag, so the flag must live in the temp folder too,
    never in the checkout that runs the suite."""
    monkeypatch.setenv("DB_PROVIDER", "sqlite")
    monkeypatch.setenv("DB_PATH", str(tmp_path / DATABASE))
    monkeypatch.setenv("STORAGE_PATH", str(tmp_path / "storage"))
    monkeypatch.setenv("UPDATE_KEEP_BACKUPS", keep)
    monkeypatch.setattr(maintenance, "project_root", lambda: tmp_path / "project")


def test_a_prune_refuses_while_a_restore_holds_the_flag(
    tmp_path: Path, monkeypatch, capsys
):
    """A copy removed while `restore` links its files back would return with files missing."""
    copies = update_copies(tmp_path, 3)
    command_env(tmp_path, monkeypatch, "1")
    maintenance.begin(f"restore {copies[0]}")
    try:
        assert prune_command() == EXIT_PRUNE_FAILED
    finally:
        maintenance.end()

    assert "nothing was removed" in capsys.readouterr().err
    assert all(path.exists() for path in copies)


def test_the_flag_is_held_while_copies_go_and_lowered_after(tmp_path: Path, monkeypatch):
    copies = update_copies(tmp_path, 2)
    command_env(tmp_path, monkeypatch, "1")
    seen_flag: list[bool] = []
    real_rmtree = shutil.rmtree

    def watching(path, *args, **kwargs):
        seen_flag.append(maintenance.is_active())
        return real_rmtree(path, *args, **kwargs)

    monkeypatch.setattr(shutil, "rmtree", watching)

    assert prune_command() == EXIT_PRUNED

    assert seen_flag == [True]
    assert not copies[0].exists()
    assert not maintenance.flag_path().exists()


def test_the_dry_run_lists_and_removes_nothing(tmp_path: Path, monkeypatch, capsys):
    copies = update_copies(tmp_path, 3)
    command_env(tmp_path, monkeypatch, "1")

    assert prune_command(dry_run=True) == EXIT_PRUNED

    printed = capsys.readouterr().out
    assert all(path.exists() for path in copies)
    assert printed.count("would remove:") == 2
    assert f"keeping: {copies[2]}" in printed


def test_the_command_reads_the_count_from_the_environment(tmp_path: Path, monkeypatch, capsys):
    copies = update_copies(tmp_path, 3)
    command_env(tmp_path, monkeypatch, "2")

    assert prune_command(spare=str(copies[2])) == EXIT_PRUNED

    assert [path.exists() for path in copies] == [False, True, True]
    assert f"removing: {copies[0]}" in capsys.readouterr().out


def test_the_command_refuses_a_negative_count(tmp_path: Path, monkeypatch, capsys):
    copies = update_copies(tmp_path, 2)
    command_env(tmp_path, monkeypatch, "-1")

    assert prune_command() == EXIT_PRUNE_FAILED

    assert "nothing was removed" in capsys.readouterr().err
    assert all(path.exists() for path in copies)


def test_the_command_fails_when_a_copy_would_not_go(tmp_path: Path, monkeypatch, capsys):
    update_copies(tmp_path, 2)
    command_env(tmp_path, monkeypatch, "1")

    def refuse(path, *args, **kwargs):
        raise PermissionError(13, "Permission denied")

    monkeypatch.setattr(shutil, "rmtree", refuse)

    assert prune_command() == EXIT_PRUNE_FAILED
    assert "remove it by hand" in capsys.readouterr().err


def test_ctrl_c_stops_the_prune_names_the_half_removed_copy_and_exits_1(
    tmp_path: Path, monkeypatch, capsys
):
    copies = update_copies(tmp_path, 4)
    command_env(tmp_path, monkeypatch, "1")
    real_rmtree = shutil.rmtree

    def interrupted(path, *args, **kwargs):
        if Path(path) == copies[2]:
            raise KeyboardInterrupt
        return real_rmtree(path, *args, **kwargs)

    monkeypatch.setattr(shutil, "rmtree", interrupted)

    assert prune_command() == EXIT_PRUNE_FAILED

    printed = capsys.readouterr().err
    assert "interrupted" in printed
    assert f"{copies[2]} is half-removed" in printed
    assert [path.exists() for path in copies] == [True, True, True, True]
    assert not (copies[2] / MANIFEST_NAME).exists()
    assert (copies[1] / MANIFEST_NAME).exists() and (copies[0] / MANIFEST_NAME).exists()
    assert not maintenance.flag_path().exists()


@pytest.mark.skipif(
    threading.current_thread() is not threading.main_thread(),
    reason="signal handlers belong to the main thread",
)
def test_a_real_ctrl_c_lets_the_copy_at_hand_go_whole_then_stops(
    tmp_path: Path, monkeypatch, capsys
):
    """The press lands mid-removal; the copy still goes whole — a half-removed one the retention
    never touches again — and the ones after it stay."""
    copies = update_copies(tmp_path, 4)
    command_env(tmp_path, monkeypatch, "1")
    real_rmtree = shutil.rmtree

    def pressed_midway(path, *args, **kwargs):
        if Path(path) == copies[2]:
            signal.raise_signal(signal.SIGINT)
        return real_rmtree(path, *args, **kwargs)

    monkeypatch.setattr(shutil, "rmtree", pressed_midway)
    handler_before = signal.getsignal(signal.SIGINT)
    try:
        code = prune_command()
    except KeyboardInterrupt:
        code = "the press escaped the command"
    finally:
        signal.signal(signal.SIGINT, handler_before)

    assert code == EXIT_PRUNE_FAILED
    assert "interrupted" in capsys.readouterr().err
    assert [path.exists() for path in copies] == [True, True, False, True]
    assert (copies[1] / MANIFEST_NAME).exists() and (copies[0] / MANIFEST_NAME).exists()
    assert not maintenance.flag_path().exists()


@pytest.mark.skipif(os.geteuid() == 0, reason="root reads a folder whatever its mode")
def test_a_backup_folder_that_cannot_be_read_is_a_refusal(tmp_path: Path, monkeypatch, capsys):
    update_copies(tmp_path, 2)
    command_env(tmp_path, monkeypatch, "1")
    folder = folder_of(tmp_path)
    folder.chmod(0o000)
    try:
        assert prune_command() == EXIT_PRUNE_FAILED
        assert prune_command(dry_run=True) == EXIT_PRUNE_FAILED
    finally:
        folder.chmod(0o755)

    assert "the backup folder cannot be read" in capsys.readouterr().err
    assert len(list(folder.iterdir())) == 2


def test_a_flag_that_cannot_be_raised_removes_nothing(tmp_path: Path, monkeypatch, capsys):
    copies = update_copies(tmp_path, 2)
    command_env(tmp_path, monkeypatch, "1")

    def read_only_runtime(reason: str):
        raise PermissionError(13, "Permission denied", "runtime/maintenance.json")

    monkeypatch.setattr(maintenance, "begin", read_only_runtime)

    assert prune_command() == EXIT_PRUNE_FAILED

    assert "the maintenance flag cannot be raised" in capsys.readouterr().err
    assert all(path.exists() for path in copies)


def test_ctrl_c_while_planning_removes_nothing_and_exits_1(tmp_path: Path, monkeypatch, capsys):
    copies = update_copies(tmp_path, 2)
    command_env(tmp_path, monkeypatch, "1")

    def interrupted(config, *, keep, spare=None):
        raise KeyboardInterrupt

    monkeypatch.setattr(backup_retention, "plan_prune", interrupted)

    assert prune_command() == EXIT_PRUNE_FAILED

    printed = capsys.readouterr().err
    assert "interrupted" in printed and "nothing was removed" in printed
    assert all(path.exists() for path in copies)
    assert not maintenance.flag_path().exists()
