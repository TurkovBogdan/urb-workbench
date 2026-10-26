"""Addresses of the module's routes: a path under ``/storage``, and that path made absolute.

The absolute form is built from ``server_host``/``server_port`` the way the app's other links are
(the stdio shim, ``interface_open``): the app is local and the backend serves everything itself.
A client that reached the server at another address gets the path and prefixes its own.
"""

from __future__ import annotations

from urllib.parse import quote

from src.core.config import get_config
from src.core.router.storage import STORAGE_PREFIX
from src.modules.core_storage_view.constants import DOWNLOAD_SEGMENT, PUBLIC_STORE, ROUTER_PREFIX


def public_file_path(code: str) -> str:
    """``/storage/public/<CODE>`` — the address the file is opened at."""
    return f"{STORAGE_PREFIX}{ROUTER_PREFIX}/{PUBLIC_STORE}/{code.strip().upper()}"


def public_download_path(code: str, name: str = "") -> str:
    """``/storage/public/<CODE>/download/<name>`` — the address that saves the file as ``name``;
    without one, under its code. A name of dots only (``..``) would step out of the path in a
    browser, so it goes as none."""
    path = f"{public_file_path(code)}/{DOWNLOAD_SEGMENT}"
    return f"{path}/{quote(name, safe='')}" if name.strip(".") else path


def app_url(path: str) -> str:
    config = get_config()
    host = config.server_host if config.server_host not in ("", "0.0.0.0") else "127.0.0.1"
    return f"http://{host}:{config.server_port}{path}"


__all__ = ["app_url", "public_download_path", "public_file_path"]
