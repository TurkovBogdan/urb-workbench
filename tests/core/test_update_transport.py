"""The HTTPS twin of an SSH origin: which addresses get one, and which never may."""

from __future__ import annotations

import pytest

from src.core.update.transport import https_options, https_twin

pytestmark = pytest.mark.pure


@pytest.mark.parametrize(
    ("remote_url", "twin"),
    [
        ("git@github.com:owner/repo.git", "https://github.com/owner/repo.git"),
        ("git@github.com:owner/repo", "https://github.com/owner/repo"),
        ("git@git.example.org:/group/sub/repo.git", "https://git.example.org/group/sub/repo.git"),
        ("ssh://git@github.com/owner/repo.git", "https://github.com/owner/repo.git"),
        ("ssh://github.com/owner/repo.git", "https://github.com/owner/repo.git"),
        ("ssh://git@git.example.org:2222/owner/repo.git", "https://git.example.org/owner/repo.git"),
        ("git+ssh://git@github.com/owner/repo.git", "https://github.com/owner/repo.git"),
    ],
)
def test_an_ssh_address_has_an_https_twin(remote_url: str, twin: str):
    assert https_twin(remote_url) == twin


@pytest.mark.parametrize(
    "remote_url",
    [
        "https://github.com/owner/repo.git",
        "http://github.com/owner/repo.git",
        "file:///srv/repo.git",
        "/srv/repo.git",
        "../repo",
        "dir:file",
        "",
    ],
)
def test_anything_but_ssh_has_no_twin(remote_url: str):
    assert https_twin(remote_url) is None
    assert https_options(remote_url) == ()


@pytest.mark.parametrize(
    "remote_url",
    [
        "git@-oProxyCommand=evil:owner/repo.git",
        "git@github.com:owner/repo.git=x",
        "git@github.com:../../etc/passwd",
        "git@github.com:owner/repo.git --upload-pack=evil",
        "ssh://git@github.com/owner/repo.git\n[core]",
        "git@github.com:",
    ],
)
def test_a_hostile_address_has_no_twin(remote_url: str):
    """The twin lands inside `-c name=value`; an `=`, a leading `-` or a traversal must not."""
    assert https_twin(remote_url) is None


def test_the_options_rewrite_exactly_this_origin():
    remote_url = "git@github.com:owner/repo.git"

    assert https_options(remote_url) == (
        "-c",
        "url.https://github.com/owner/repo.git.insteadOf=git@github.com:owner/repo.git",
    )
