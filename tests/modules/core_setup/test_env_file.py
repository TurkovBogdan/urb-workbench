"""core_setup: the line-based .env editor — comments preserved + in-place edits."""

from __future__ import annotations

import os
from types import SimpleNamespace

import pytest

from src.modules.core_setup import env_file
from src.modules.core_setup.keys import FIELDS


def _fake_config(**over) -> SimpleNamespace:
    """Config stand-in: one attribute per ENV key of the form (key in lower case)."""
    values = {f.key.lower(): "" for f in FIELDS}
    values.update({s.key.lower(): "" for s in env_file.SECRETS})
    values.update(over)
    return SimpleNamespace(**values)


@pytest.mark.pure
def test_write_preserves_comments_replaces_in_place_appends_missing(tmp_path, monkeypatch):
    path = tmp_path / ".env"
    path.write_text(
        "# header comment\n"
        "DB_PROVIDER=postgres\n"
        "# inline doc for port\n"
        "DB_PORT=5432\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(env_file, "env_path", lambda: path)

    env_file.write_values({"DB_PROVIDER": "sqlite", "NEW_KEY": "x"})

    text = path.read_text(encoding="utf-8")
    assert "# header comment" in text  # comments preserved
    assert "# inline doc for port" in text
    assert "DB_PROVIDER=sqlite" in text  # replaced in place
    assert "DB_PORT=5432" in text  # untouched key
    assert "NEW_KEY=x" in text  # appended at the end
    # the order of the original lines is intact
    assert text.index("DB_PROVIDER") < text.index("DB_PORT") < text.index("NEW_KEY")


@pytest.mark.pure
def test_read_values_picks_only_requested_keys(tmp_path, monkeypatch):
    path = tmp_path / ".env"
    path.write_text("DB_PROVIDER=sqlite\nDB_PORT=5432\nIGNORED=1\n", encoding="utf-8")
    monkeypatch.setattr(env_file, "env_path", lambda: path)

    assert env_file.read_values(["DB_PROVIDER", "DB_PORT"]) == {
        "DB_PROVIDER": "sqlite",
        "DB_PORT": "5432",
    }


@pytest.mark.pure
def test_seed_creates_env_with_defaults_when_absent(tmp_path, monkeypatch):
    path = tmp_path / ".env"
    monkeypatch.setattr(env_file, "env_path", lambda: path)
    config = _fake_config(
        db_provider="sqlite", db_ssl=True, db_port=5432,
        server_port=13410, server_vite_port=None, worker_enabled=False,
    )

    created = env_file.seed_defaults_if_absent(config)

    assert created is True
    values = env_file.read_values([f.key for f in FIELDS])
    assert {f.key for f in FIELDS} <= set(values)  # every form field is written
    assert values["DB_PROVIDER"] == "sqlite"
    assert values["DB_SSL"] == "true"  # bool → true/false
    assert values["SERVER_PORT"] == "13410"  # int → string
    assert values["SERVER_VITE_PORT"] == ""  # None → empty
    assert values["WORKER_ENABLED"] == "false"
    assert path.stat().st_mode & 0o777 == 0o600  # the file holds secrets — owner-only read


@pytest.mark.pure
def test_seed_is_noop_when_env_exists(tmp_path, monkeypatch):
    path = tmp_path / ".env"
    path.write_text("DB_PROVIDER=postgres\n", encoding="utf-8")
    monkeypatch.setattr(env_file, "env_path", lambda: path)

    created = env_file.seed_defaults_if_absent(_fake_config(db_provider="sqlite"))

    assert created is False
    assert path.read_text(encoding="utf-8") == "DB_PROVIDER=postgres\n"  # untouched


@pytest.mark.pure
def test_a_key_added_after_the_file_was_written_is_topped_up(tmp_path, monkeypatch):
    """Otherwise a key introduced in a new version never reaches any live installation:
    `seed_defaults_if_absent` only writes a missing file (this happened with UPDATE_BRANCH)."""
    path = tmp_path / ".env"
    path.write_text("# оператор правил руками\nDB_PROVIDER=postgres\n", encoding="utf-8")
    monkeypatch.setattr(env_file, "env_path", lambda: path)

    added = env_file.ensure_keys_present(_fake_config(update_branch="main"))

    assert "UPDATE_BRANCH" in added
    assert "DB_PROVIDER" not in added
    text = path.read_text(encoding="utf-8")
    assert "UPDATE_BRANCH=main" in text
    assert "DB_PROVIDER=postgres" in text  # the existing value is untouched
    assert "# оператор правил руками" in text
    assert "# Update branch" in text  # the key is explained, not dumped as a bare line


@pytest.mark.pure
def test_topping_up_is_idempotent_and_never_touches_a_full_file(tmp_path, monkeypatch):
    path = tmp_path / ".env"
    monkeypatch.setattr(env_file, "env_path", lambda: path)
    env_file.seed_defaults_if_absent(_fake_config(update_branch="dev"))
    before = path.read_text(encoding="utf-8")

    assert env_file.ensure_keys_present(_fake_config(update_branch="main")) == []
    assert path.read_text(encoding="utf-8") == before


@pytest.mark.pure
def test_topping_up_does_not_create_a_missing_file(tmp_path, monkeypatch):
    """Creating the file is `seed_defaults_if_absent`'s job; this is only a live installation."""
    path = tmp_path / ".env"
    monkeypatch.setattr(env_file, "env_path", lambda: path)

    assert env_file.ensure_keys_present(_fake_config()) == []
    assert path.exists() is False


@pytest.fixture
def env(tmp_path, monkeypatch):
    """`.env` in a temp directory + a guarantee that secrets don't leak into the test environment.

    ``setenv`` before calling the code: monkeypatch remembers the variable's original state and
    restores it on exit, even if the code overwrites it directly via ``os.environ``.
    """
    path = tmp_path / ".env"
    path.write_text("DB_PROVIDER=sqlite\n", encoding="utf-8")
    monkeypatch.setattr(env_file, "env_path", lambda: path)
    for secret in env_file.SECRETS:
        monkeypatch.setenv(secret.key, "")
    return path


@pytest.mark.pure
def test_missing_secrets_are_generated_into_an_existing_env(env):
    generated = env_file.ensure_generated(_fake_config())

    assert set(generated) == {s.key for s in env_file.SECRETS}
    values = env_file.read_values(generated)
    assert all(values[key] for key in generated)
    text = env.read_text(encoding="utf-8")
    assert "DB_PROVIDER=sqlite" in text  # the existing file is not rewritten
    assert "# Master key encrypting" in text  # the key is explained, not dumped as a bare line
    assert env.stat().st_mode & 0o777 == 0o600


@pytest.mark.pure
def test_a_generated_secret_is_taken_into_use_right_away(env):
    env_file.ensure_generated(_fake_config())

    # Written → adopted: the process that issued it already encrypts with this key
    assert os.environ["SECRETS_KEY"] == env_file.read_values(["SECRETS_KEY"])["SECRETS_KEY"]


@pytest.mark.pure
def test_an_existing_value_is_never_overwritten(env):
    generated = env_file.ensure_generated(_fake_config(secrets_key="ключ-оператора"))

    assert "SECRETS_KEY" not in generated
    assert "SECRETS_KEY" not in env_file.read_values(["SECRETS_KEY"])


@pytest.mark.pure
def test_generation_is_idempotent(env):
    first = env_file.ensure_generated(_fake_config())
    value = env_file.read_values(["SECRETS_KEY"])["SECRETS_KEY"]

    second = env_file.ensure_generated(_fake_config(secrets_key=value))

    assert first and second == []
    assert env_file.read_values(["SECRETS_KEY"])["SECRETS_KEY"] == value


@pytest.mark.pure
def test_a_key_written_by_a_neighbour_process_is_adopted_not_regenerated(env):
    # Config is empty (read before the neighbour wrote), but the file already has a key — must not
    # generate, or the two would encrypt with different keys while the file keeps only one
    env.write_text(env.read_text(encoding="utf-8") + "SECRETS_KEY=сосед\n", encoding="utf-8")

    generated = env_file.ensure_generated(_fake_config())

    assert "SECRETS_KEY" not in generated
    assert env_file.read_values(["SECRETS_KEY"])["SECRETS_KEY"] == "сосед"


@pytest.mark.pure
def test_a_key_that_could_not_be_written_is_not_taken_into_use(env, monkeypatch):
    def _fail(*_args, **_kwargs):
        raise OSError("read-only file system")

    monkeypatch.setattr(env_file, "write_values", _fail)

    generated = env_file.ensure_generated(_fake_config())

    # A key held only in memory would encrypt records that become unreadable after a restart
    assert generated == []
    assert os.environ["SECRETS_KEY"] == ""


@pytest.mark.pure
def test_the_generated_master_key_keeps_its_declared_format(env):
    """32 random bytes in unpadded base64url — what the generator's docstring promises.

    The format used to be checked against the encryption layer that consumed the key
    (``core_connectors``); that module is gone, the contract has no other side, so what remains to
    check is the promise itself. When a consumer returns, the test goes back to it, not this shape.
    """
    import base64

    env_file.ensure_generated(_fake_config())
    key = env_file.read_values(["SECRETS_KEY"])["SECRETS_KEY"]

    assert "=" not in key
    assert len(base64.urlsafe_b64decode(key + "=" * (-len(key) % 4))) == 32
