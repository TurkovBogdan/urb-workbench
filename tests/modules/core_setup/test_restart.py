"""core_setup: predicting where a restart moves the server — the address the settings page follows."""

from __future__ import annotations

import pytest

from src.modules.core_setup import restart


@pytest.fixture
def next_address(monkeypatch):
    """What the restarted image will read: the environment outweighs `.env` in Config."""

    def set_(host: str, port: int) -> None:
        monkeypatch.setenv("SERVER_HOST", host)
        monkeypatch.setenv("SERVER_PORT", str(port))

    return set_


@pytest.mark.pure
def test_new_port_is_reported_with_the_address_it_leaves(next_address):
    next_address("127.0.0.1", 22150)

    move = restart.predict_move(hot_reload=False, bound_host="127.0.0.1", bound_port=22140)

    assert move == {"host": "127.0.0.1", "port": 22150, "from_host": "127.0.0.1", "from_port": 22140}


@pytest.mark.pure
def test_new_host_is_reported(next_address):
    next_address("0.0.0.0", 22140)

    move = restart.predict_move(hot_reload=False, bound_host="127.0.0.1", bound_port=22140)

    assert move is not None
    assert (move["host"], move["port"]) == ("0.0.0.0", 22140)


@pytest.mark.pure
def test_same_address_is_no_move(next_address):
    next_address("127.0.0.1", 22140)

    assert restart.predict_move(hot_reload=False, bound_host="127.0.0.1", bound_port=22140) is None


@pytest.mark.pure
def test_hot_reload_keeps_the_socket_whatever_env_says(next_address):
    next_address("0.0.0.0", 22150)

    assert restart.predict_move(hot_reload=True, bound_host="127.0.0.1", bound_port=22140) is None


@pytest.mark.pure
def test_config_that_cannot_load_is_no_move(next_address, monkeypatch):
    next_address("127.0.0.1", 22150)
    monkeypatch.setenv("DB_PROVIDER", "postgres")
    monkeypatch.setenv("DB_HOST", "")

    assert restart.predict_move(hot_reload=False, bound_host="127.0.0.1", bound_port=22140) is None
