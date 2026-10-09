"""`app.py stop`: the plan is printed before any signal, refusals become exit codes.

The command is a thin wrapper over the same layer that stops the install during an update, so
only its own half is tested: that the plan is shown, that a dry run sends nothing, that every
refusal reaches an exit code instead of turning into a traceback for whoever ran `./run.sh stop`.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.core.update import sequence
from src.core.update.sequence import (
    EXIT_OK,
    EXIT_STOP_FAILED,
    EXIT_UNREGISTERED,
    EXIT_UNSUPPORTED_PLATFORM,
    stop_command,
)
from src.core.update.stop import (
    ForeignProcesses,
    OwnIdentity,
    ProcessesSurvived,
    StopPlan,
    StopTarget,
    UnregisteredProcesses,
    UpdaterInsideInstall,
)

CHECKOUT = Path("/tmp/install")
BACKEND_PID = 4242


def _plan() -> StopPlan:
    return StopPlan(
        checkout=CHECKOUT,
        own=OwnIdentity(pid=1, pgid=1),
        singles=(
            StopTarget(
                pid=BACKEND_PID,
                start_time=1.0,
                command_line="src/app.py --backend --worker",
                matched_as="recorded",
            ),
        ),
    )


@pytest.fixture
def planned(monkeypatch):
    """Replace planning against the live machine; return a log of the arguments passed to it."""
    asked: list[dict] = []

    def fake_plan_live_stop(checkout, *, stop_unregistered=False):
        asked.append({"checkout": checkout, "stop_unregistered": stop_unregistered})
        return _plan()

    monkeypatch.setattr(sequence, "plan_live_stop", fake_plan_live_stop)
    return asked


@pytest.fixture
def signalled(monkeypatch):
    """Replace signal delivery; return a log of the plans that reached it."""
    signalled_plans: list[StopPlan] = []

    def fake_execute_stop(plan, **kwargs):
        signalled_plans.append(plan)
        return []

    monkeypatch.setattr(sequence, "execute_stop", fake_execute_stop)
    return signalled_plans


def _refuse_with(monkeypatch, refusal: Exception) -> None:
    def refuse(plan, **kwargs):
        raise refusal

    monkeypatch.setattr(sequence, "execute_stop", refuse)


def _forbid_signals(monkeypatch) -> None:
    """Sending a signal in this test is a failure, not one of the paths."""

    def forbidden(plan, **kwargs):
        raise AssertionError("a signal was sent where there must be none")

    monkeypatch.setattr(sequence, "execute_stop", forbidden)


@pytest.mark.pure
def test_the_plan_is_printed_and_then_signalled(planned, signalled, capsys):
    assert stop_command() == EXIT_OK

    assert len(signalled) == 1
    printed = capsys.readouterr().out
    assert str(BACKEND_PID) in printed
    assert str(CHECKOUT) in printed


@pytest.mark.pure
def test_a_dry_run_prints_the_plan_and_signals_nothing(planned, monkeypatch, capsys):
    """A dry run must be a safe answer to "what would you stop?"."""
    _forbid_signals(monkeypatch)

    assert stop_command(dry_run=True) == EXIT_OK
    assert str(BACKEND_PID) in capsys.readouterr().out


@pytest.mark.pure
def test_stop_unregistered_reaches_the_planner(planned, signalled):
    """The flag changes the plan, not signal behaviour: whether to stop without a record or
    refuse is decided at planning time."""
    stop_command(stop_unregistered=True)

    assert planned[-1]["stop_unregistered"] is True


@pytest.mark.pure
def test_processes_without_a_record_end_as_exit_10(planned, monkeypatch, capsys):
    """The same code as the update's: unregistered processes are a refusal, not a silent stop
    on circumstantial evidence."""
    _refuse_with(monkeypatch, UnregisteredProcesses("pid 4242 looks like this install"))

    assert stop_command() == EXIT_UNREGISTERED
    assert "refusing to stop" in capsys.readouterr().out


@pytest.mark.pure
@pytest.mark.parametrize(
    "refusal",
    [
        ProcessesSurvived("still alive after TERM and KILL"),
        ForeignProcesses("pid 4242 belongs to another user"),
        UpdaterInsideInstall("the updater shares process group 7 with the install"),
    ],
    ids=["survived", "another user", "own group"],
)
def test_an_install_that_did_not_stop_is_never_reported_as_stopped(
    planned, monkeypatch, capsys, refusal
):
    _refuse_with(monkeypatch, refusal)

    assert stop_command() == EXIT_STOP_FAILED
    assert "refusing to stop" in capsys.readouterr().out


@pytest.mark.pure
def test_windows_is_refused_with_a_message_not_a_traceback(planned, monkeypatch, capsys):
    """Stopping is built on POSIX process groups; on Windows the command must say so in
    words — a traceback from deep inside won't tell anyone what to do."""
    monkeypatch.setattr(sequence.sys, "platform", "win32")

    assert stop_command() == EXIT_UNSUPPORTED_PLATFORM
    assert "Windows" in capsys.readouterr().out
    assert planned == []
