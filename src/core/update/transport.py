"""The HTTPS way back to an origin that is recorded over SSH.

Updates run without a terminal, so ssh runs in batch mode — and a developer checkout whose key
needs a passphrase or an agent the updater cannot see is then refused outright. The project is
public: reading it needs no key at all, so a refused SSH origin is asked again over HTTPS.

The rewrite is per command (`git -c url.<https>.insteadOf=<ssh>`), never written to `.git/config`:
the developer's push keeps going over SSH.

The address comes out of git's own config, but it still ends up inside a `-c name=value`
argument, so only a narrow alphabet is accepted: nothing may start with `-`, and `=` — the
separator git splits that argument on — cannot appear at all.
"""

from __future__ import annotations

import re

_HOST = r"(?P<host>[A-Za-z0-9][A-Za-z0-9.-]*)"
_PATH = r"(?P<path>[A-Za-z0-9._~/-]+)"
_USER = r"[A-Za-z0-9][A-Za-z0-9._-]*@"

# `git@github.com:owner/repo.git` — scp-like; the user is required, or a local `dir:file` path
# would read as a host.
_SCP_LIKE = re.compile(rf"{_USER}{_HOST}:/?{_PATH}")
# `ssh://git@host:2222/owner/repo.git` — the port is the SSH daemon's, not the web server's.
_SSH_URL = re.compile(rf"(?:git\+)?ssh://(?:{_USER})?{_HOST}(?::\d+)?/{_PATH}")


def https_twin(remote_url: str) -> str | None:
    """`https://host/path` for an SSH address; `None` for anything else or anything suspicious."""
    matched = _SCP_LIKE.fullmatch(remote_url) or _SSH_URL.fullmatch(remote_url)
    if matched is None:
        return None
    path = matched["path"].lstrip("/")
    if not path or ".." in path:
        return None
    return f"https://{matched['host']}/{path}"


def https_options(remote_url: str) -> tuple[str, ...]:
    """git options that send this one command to the HTTPS twin; empty when there is none."""
    twin = https_twin(remote_url)
    if twin is None:
        return ()
    return ("-c", f"url.{twin}.insteadOf={remote_url}")


__all__ = ["https_options", "https_twin"]
