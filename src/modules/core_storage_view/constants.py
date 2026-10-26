"""Constants of serving: which store is served, which types are sandboxed."""

from __future__ import annotations

# The one place that names the module's log channel.
LOG_CHANNEL = "core_storage_view"

# The module's route sits right under the zone: ``/storage/<store>/<code>``.
ROUTER_PREFIX = ""

# ``/storage/<store>/<code>/download[/<name>]`` saves the file instead of opening it.
DOWNLOAD_SEGMENT = "download"

# What a store means is not the storage's knowledge; here it is decided: only ``public`` leaves
# the backend. ``private`` and any store a project adds stay closed until named here.
PUBLIC_STORE = "public"
SERVED_STORES = frozenset({PUBLIC_STORE})

# The files are served from the app's own origin, so a document that can run script would run it
# with the app's rights. These types get ``Content-Security-Policy: sandbox``; so does every
# ``+xml`` type — XML rendered by the browser can pull in XSLT and script.
SANDBOXED_MIMES = frozenset(
    {
        "text/html",
        "application/xhtml+xml",
        "application/xml",
        "text/xml",
        "image/svg+xml",
    }
)
SANDBOXED_SUFFIX = "+xml"

__all__ = [
    "DOWNLOAD_SEGMENT",
    "LOG_CHANNEL",
    "PUBLIC_STORE",
    "ROUTER_PREFIX",
    "SANDBOXED_MIMES",
    "SANDBOXED_SUFFIX",
    "SERVED_STORES",
]
