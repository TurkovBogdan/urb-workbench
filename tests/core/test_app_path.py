"""AppPath + ensure_dirs."""

from __future__ import annotations

import pytest

from pathlib import Path

from src.core.app_path import AppPath, ensure_dirs


@pytest.mark.pure
def test_from_root_explicit(tmp_path: Path):
    paths = AppPath.from_root(tmp_path)
    assert paths.root == tmp_path
    assert paths.logs == tmp_path / "logs"
    assert paths.cache == tmp_path / "cache"
    assert paths.user == tmp_path / "user"


@pytest.mark.pure
def test_from_root_resolves_runtime_when_no_arg():
    paths = AppPath.from_root()
    assert paths.root.is_absolute()
    assert paths.logs == paths.root / "logs"
    assert paths.cache == paths.root / "cache"
    assert paths.user == paths.root / "user"


@pytest.mark.pure
def test_ensure_dirs_creates(tmp_path: Path):
    paths = AppPath.from_root(tmp_path / "nested" / "root")
    ensure_dirs(paths)
    assert paths.root.is_dir()
    assert paths.logs.is_dir()
    assert paths.cache.is_dir()
    assert paths.user.is_dir()


@pytest.mark.pure
def test_ensure_dirs_idempotent(tmp_path: Path):
    paths = AppPath.from_root(tmp_path)
    ensure_dirs(paths)
    ensure_dirs(paths)  # must not fail


@pytest.mark.pure
def test_app_env_changes_runtime_root(monkeypatch, tmp_path: Path):
    """The resolver takes APP_ENV from env (non-frozen only)."""
    monkeypatch.setenv("APP_ENV", "test_env_xyz")
    paths = AppPath.from_root()
    assert "test_env_xyz" in str(paths.root)
