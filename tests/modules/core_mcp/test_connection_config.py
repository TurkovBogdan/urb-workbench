"""core_mcp: generating the stdio connection config (passing MCP_TOKEN / code / workspace)."""

from __future__ import annotations

import json

import pytest

from src.modules.core_mcp.api import _stdio_config


def _server(code="research", *, pin_code=False, token="", workspace=""):
    return json.loads(
        _stdio_config(code, pin_code=pin_code, token=token, workspace=workspace)
    )["mcpServers"][f"urb-{code}"]


@pytest.mark.pure
def test_stdio_config_names_the_server_with_the_brand_not_the_bare_code():
    """In a client the server sits among others — a bare ``workbench`` doesn't say whose it is."""
    config = json.loads(_stdio_config("workbench", pin_code=False, token="", workspace=""))

    assert list(config["mcpServers"]) == ["urb-workbench"]


@pytest.mark.pure
def test_stdio_config_keeps_the_token_in_env_not_in_args():
    """Args are visible in ``ps`` machine-wide — no secret goes there, the server code may."""
    server = _server(token="secret-xyz")

    assert server["env"] == {"MCP_TOKEN": "secret-xyz"}
    assert "secret-xyz" not in server["args"]


@pytest.mark.pure
def test_stdio_config_no_env_without_token_single_server():
    server = _server()

    assert "env" not in server  # no token — no env needed at all
    assert server["args"][-1] == "--mcp-stdio"  # single server → the code is not pinned


@pytest.mark.pure
def test_stdio_config_pins_the_server_code_as_an_argument():
    server = _server("workbench", pin_code=True, token="t")

    assert server["args"][-1] == "--mcp-stdio=workbench"
    assert server["env"] == {"MCP_TOKEN": "t"}


@pytest.mark.pure
def test_stdio_config_carries_the_configured_workspace():
    """The configured workspace goes into the config: the connection starts already bound."""
    server = _server("workbench", pin_code=True, workspace="WORKSPACE@18e948522f")

    assert server["args"][-2:] == [
        "--mcp-stdio=workbench", "--mcp-workspace=WORKSPACE@18e948522f",
    ]


@pytest.mark.pure
def test_stdio_config_glues_value_to_flag():
    """A glued pair can't fall apart under a manual edit — there is no separate half to lose.

    For ``--mcp-stdio`` this is not cosmetic: its value is optional, so an orphaned flag won't
    fail, it will quietly change meaning to "pick the server yourself".
    """
    args = _server("workbench", pin_code=True, workspace="WORKSPACE@1")["args"]

    assert "workbench" not in args  # not as a separate element
    assert "--mcp-workspace" not in args


@pytest.mark.pure
def test_stdio_config_omits_an_unset_workspace():
    """An empty argument would read as a required field someone forgot to fill in."""
    server = _server("workbench", token="t")

    assert not any(a.startswith("--mcp-workspace") for a in server["args"])


@pytest.mark.pure
def test_the_generated_args_parse_back_into_the_same_intent():
    """The only test that ties the generator to its consumer.

    Each side can be edited on its own and both stay "correct" — they turn out to have diverged
    only when a person copies the config and gets "Connection Failed". Here the output is handed
    to exactly the parser that will read it for real.
    """
    import app

    args = _server("workbench", pin_code=True, workspace="WORKSPACE@18e948522f")["args"]
    # Cut off the `uv` part — the shim gets everything after the script name.
    parsed = app._parse_args(args[args.index("src/app.py") + 1:])

    assert parsed.mcp_stdio == "workbench"
    assert parsed.mcp_workspace == "WORKSPACE@18e948522f"
