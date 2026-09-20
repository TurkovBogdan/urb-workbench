"""core_mcp: генерация stdio-конфига подключения (проброс MCP_TOKEN / кода / пространства)."""

from __future__ import annotations

import json

import pytest

from src.modules.core_mcp.api import _stdio_config


def _server(code="research", *, pin_code=False, token="", workspace=""):
    return json.loads(
        _stdio_config(code, pin_code=pin_code, token=token, workspace=workspace)
    )["mcpServers"][code]


@pytest.mark.pure
def test_stdio_config_keeps_the_token_in_env_not_in_args():
    """Аргументы видны в ``ps`` всей машине — секрет туда не кладут, а код сервера можно."""
    server = _server(token="secret-xyz")

    assert server["env"] == {"MCP_TOKEN": "secret-xyz"}
    assert "secret-xyz" not in server["args"]


@pytest.mark.pure
def test_stdio_config_no_env_without_token_single_server():
    server = _server()

    assert "env" not in server  # токена нет — env не нужен вовсе
    assert server["args"][-1] == "--mcp-stdio"  # один сервер → код не пинуем


@pytest.mark.pure
def test_stdio_config_pins_the_server_code_as_an_argument():
    server = _server("workbench", pin_code=True, token="t")

    assert server["args"][-1] == "--mcp-stdio=workbench"
    assert server["env"] == {"MCP_TOKEN": "t"}


@pytest.mark.pure
def test_stdio_config_carries_the_configured_workspace():
    """Настроенное пространство едет в конфиг: подключение стартует уже привязанным."""
    server = _server("workbench", pin_code=True, workspace="WORKSPACE@18e948522f")

    assert server["args"][-2:] == [
        "--mcp-stdio=workbench", "--mcp-workspace=WORKSPACE@18e948522f",
    ]


@pytest.mark.pure
def test_stdio_config_glues_value_to_flag():
    """Склеенная пара не распадается при ручной правке — половины, которую теряют, просто нет.

    Для ``--mcp-stdio`` это не косметика: значение у него необязательное, и осиротевший флаг не
    упадёт, а тихо сменит смысл на «сервер выбери сам».
    """
    args = _server("workbench", pin_code=True, workspace="WORKSPACE@1")["args"]

    assert "workbench" not in args  # не отдельным элементом
    assert "--mcp-workspace" not in args


@pytest.mark.pure
def test_stdio_config_omits_an_unset_workspace():
    """Пустой аргумент читался бы как обязательное поле, которое забыли заполнить."""
    server = _server("workbench", token="t")

    assert not any(a.startswith("--mcp-workspace") for a in server["args"])


@pytest.mark.pure
def test_the_generated_args_parse_back_into_the_same_intent():
    """Единственный тест, который связывает генератор с потребителем.

    Обе стороны можно править по отдельности и обе останутся «правильными» — разошедшимися
    они окажутся только в момент, когда человек скопирует конфиг и получит «Connection
    Failed». Здесь выданное отдаётся ровно тому разборщику, который его прочтёт в живую.
    """
    import app

    args = _server("workbench", pin_code=True, workspace="WORKSPACE@18e948522f")["args"]
    # Отрезаем часть для `uv` — шиму достаётся всё после имени скрипта.
    parsed = app._parse_args(args[args.index("src/app.py") + 1:])

    assert parsed.mcp_stdio == "workbench"
    assert parsed.mcp_workspace == "WORKSPACE@18e948522f"
