"""The codex rules as pure answers: a slug that fits a path, a depth that fits the limit."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from src.modules.codex.rules import DEPTH_MAX, agent_may_write, depth_problem, slug_problem

pytestmark = pytest.mark.pure


@pytest.mark.parametrize("slug", ["python", "vue-3", "2fa", "a" * 64])
def test_a_path_segment_is_a_slug(slug):
    assert slug_problem(slug) is None


@pytest.mark.parametrize(
    ("slug", "says"),
    [
        ("", "empty"),
        ("a" * 65, "65 characters long, the limit is 64"),
        ("Python", "only a-z"),
        ("-python", "must start"),
        ("py thon", "only a-z"),
        ("тесты", "only a-z"),
        ("py/thon", "only a-z"),
    ],
)
def test_what_cannot_be_a_path_segment_says_why(slug, says):
    assert says in slug_problem(slug)


def test_the_fourth_level_fits_and_the_fifth_does_not():
    assert DEPTH_MAX == 4
    assert depth_problem(parent_depth=3) is None
    assert "reach 5 levels, the limit is 4" in depth_problem(parent_depth=4)


def test_a_moved_branch_counts_its_own_height():
    assert depth_problem(parent_depth=2, branch_height=2) is None
    assert "1 too deep" in depth_problem(parent_depth=2, branch_height=3)


def test_the_agent_writes_only_through_a_mount_that_allows_it():
    assert agent_may_write(SimpleNamespace(agent_can_edit=True))
    assert not agent_may_write(SimpleNamespace(agent_can_edit=False))
    assert not agent_may_write(None)
