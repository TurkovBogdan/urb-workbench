"""Reading/writing ``.env`` while preserving comments and structure.

A write edits ``KEY=…`` lines IN PLACE; comments, blank lines and order are left alone.
Missing keys are appended at the end. A read takes values straight from the file (the very
source being edited), not from ``Config`` — the form shows exactly what is in ``.env``, with
no validation of intermediate states.

This is also where the installation **issues its own secrets** (``SECRETS``): the MCP surface
token and the master key encrypting values in the DB. Both are needed from the first start,
and asking a human for either is pointless — they would just generate a random string anyway.
The code lives here because the module's subject is the ``.env`` file itself; whose key ends
up in it is a secondary question.
"""

from __future__ import annotations

import base64
import fcntl
import os
import re
import secrets
from collections.abc import Iterable, Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from src.core.config import Config, _env_file, get_config
from src.core.loggers import get_logger
from src.modules.core_setup.keys import FIELDS, SetupField

_SECRET_BYTES = 32
_LOG = get_logger("core_setup")


@dataclass(frozen=True)
class GeneratedSecret:
    """A secret the installation issues to itself when it is not there yet."""

    key: str
    generate: Callable[[], str]
    comment: str


def _bearer_token() -> str:
    return secrets.token_urlsafe(_SECRET_BYTES)


def _master_key() -> str:
    """32 random bytes in base64url — the format the encryption layer expects."""
    return base64.urlsafe_b64encode(os.urandom(_SECRET_BYTES)).decode().rstrip("=")


SECRETS: tuple[GeneratedSecret, ...] = (
    GeneratedSecret(
        "MCP_TOKEN",
        _bearer_token,
        "# Static bearer for the MCP servers. Generated on first start.",
    ),
    GeneratedSecret(
        "SECRETS_KEY",
        _master_key,
        "# Master key encrypting values in the DB. Generated on first start;\n"
        "# a database copy is useless without it, and if it is lost credentials are re-entered.",
    ),
)


def env_path() -> Path:
    return _env_file()


def _config_default(field: SetupField, config: Config) -> str:
    """The field's default from ``Config``: the form's ENV key == the Config field lowercased
    (the pydantic-settings convention — the field name defines the ENV variable)."""
    value = getattr(config, field.key.lower())
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return ""
    return str(value)


def seed_defaults_if_absent(config: Config) -> bool:
    """First run without ``.env`` → create it with the default values from ``Config`` (the
    settings page shows the real defaults, not empty fields). Secrets are topped up by
    ``ensure_generated``, called right after. Returns True if the file was created."""
    if env_path().is_file():
        return False
    write_values({f.key: _config_default(f, config) for f in FIELDS})
    _restrict_access()
    return True


def ensure_keys_present(config: Config) -> list[str]:
    """Append to an EXISTING ``.env`` the form keys it does not have yet.

    ``seed_defaults_if_absent`` writes only a file that does not exist, so a key introduced
    in a new version (that is how ``UPDATE_BRANCH`` arrived) never reaches any live
    installation: it is neither in the file nor on the settings page, and the operator has
    nowhere to change its value. The CURRENT ``Config`` value is written (the code default if
    the key is set nowhere else) — the installation's behaviour does not change, only its
    visibility does. Returns the keys added.
    """
    if not env_path().is_file():
        return []
    with _write_lock():
        present = read_values(field.key for field in FIELDS)
        missing = [field for field in FIELDS if field.key not in present]
        if not missing:
            return []
        write_values(
            {field.key: _config_default(field, config) for field in missing},
            comments={field.key: _key_comment(field) for field in missing},
        )
        _restrict_access()
    return [field.key for field in missing]


def _key_comment(field: SetupField) -> str:
    described = f"{field.label} — {field.description}" if field.description else field.label
    return f"# {described}"


def _assignment_key(line: str) -> str | None:
    """The key of a ``KEY=value`` line (no comment/whitespace); None if it is not an assignment."""
    match = re.match(r"\s*([A-Za-z_][A-Za-z0-9_]*)\s*=", line)
    return match.group(1) if match else None


def read_values(keys: Iterable[str]) -> dict[str, str]:
    """Current values of the listed keys from ``.env`` (missing ones → skipped)."""
    wanted = set(keys)
    values: dict[str, str] = {}
    path = env_path()
    if not path.is_file():
        return values
    for line in path.read_text(encoding="utf-8").splitlines():
        key = _assignment_key(line)
        if key in wanted:
            values[key] = line.split("=", 1)[1].strip()
    return values


def write_values(updates: Mapping[str, str], comments: Mapping[str, str] | None = None) -> None:
    """Write values into ``.env``: replace ``KEY=`` lines in place, append the missing ones.

    ``comments`` is printed only above **appended** keys: people read the file by eye, and a
    key that appeared on its own with no explanation looks like garbage.
    """
    if not updates:
        return
    path = env_path()
    lines = path.read_text(encoding="utf-8").splitlines() if path.is_file() else []
    remaining = dict(updates)
    for i, line in enumerate(lines):
        key = _assignment_key(line)
        if key in remaining:
            lines[i] = f"{key}={remaining.pop(key)}"
    for key, value in remaining.items():
        comment = (comments or {}).get(key)
        if comment:
            lines.extend(["", *comment.splitlines()])
        lines.append(f"{key}={value}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _restrict_access() -> None:
    """Mode 600 on ``.env``: it holds secrets, and only the owner should read them."""
    path = env_path()
    if path.is_file():
        path.chmod(0o600)


@contextmanager
def _write_lock() -> Iterator[None]:
    """Mutual exclusion on writing ``.env`` across the installation's processes.

    The backend, the worker and a second backend spawned by the shim start simultaneously;
    without the lock two of them could generate DIFFERENT keys while only one lands in the
    file — and the other would encrypt records with a key that no longer exists.
    """
    lock_path = env_path().with_suffix(env_path().suffix + ".lock")
    with open(lock_path, "w", encoding="utf-8") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def ensure_generated(config: Config) -> list[str]:
    """Top up ``.env`` with the secrets it does not have yet. Returns the generated keys.

    The **effective** value is checked (``Config`` has already accounted for both the shell
    variable and the file): a key set by the operator is never touched. The order "write
    first, then adopt" is mandatory — a key that lived only in memory would encrypt records
    that nobody could read after a restart; so when the write fails we simply run without it.
    """
    missing = [s for s in SECRETS if not _effective(config, s.key)]
    if not missing:
        return []

    written: list[str] = []
    with _write_lock():
        for secret in missing:
            if read_values([secret.key]).get(secret.key):
                continue  # while we waited for the lock, a sibling process issued the key
            value = secret.generate()
            try:
                write_values({secret.key: value}, comments={secret.key: secret.comment})
                _restrict_access()
            except OSError as exc:
                _LOG.warning("%s not written to .env (%s) — running without it", secret.key, exc)
                continue
            os.environ[secret.key] = value
            written.append(secret.key)
    if written:
        get_config.cache_clear()
    return written


def _effective(config: Config, key: str) -> str:
    """The key's current value as the application sees it (environment over the file)."""
    return str(getattr(config, key.lower(), "") or "")


__all__ = [
    "SECRETS",
    "GeneratedSecret",
    "env_path",
    "ensure_generated",
    "ensure_keys_present",
    "read_values",
    "seed_defaults_if_absent",
    "write_values",
]
