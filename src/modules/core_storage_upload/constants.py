"""Constants of the upload: the route, the upload request and its token, the settings' defaults."""

from __future__ import annotations

# The one place that names the module's log channel.
LOG_CHANNEL = "core_storage_upload"

# The module's one route sits right under the zone: ``/storage/upload`` — the person's page and a
# client with an upload request's token alike.
ROUTER_PREFIX = ""
UPLOAD_ROUTE = "/upload"

# The token of an upload request: random bytes of a CSPRNG, url-safe. 32 bytes — 256 bits, twice
# the 128 an address that is the whole permission needs. Only its sha256 is stored.
TOKEN_BYTES = 32
TOKEN_HASH_LEN = 64

# Widths of an upload request's columns. The holder's code and the workspace's are the
# consumers' codes, whole (``NOTE@AB12CD34EF``); the name is a name the storage would keep —
# 255 characters and an extension of 16.
HOLDER_MAX = 64
WORKSPACE_MAX = 64
FILENAME_MAX = 272

REQUEST_TTL_MINUTES_DEFAULT = 15
REQUEST_TTL_MINUTES_MAX = 24 * 60
SERVER_PATH_ENABLED_DEFAULT = True

# A file read from the server's disk goes in pieces of this size.
CHUNK_SIZE = 1024 * 1024

__all__ = [
    "CHUNK_SIZE",
    "FILENAME_MAX",
    "HOLDER_MAX",
    "LOG_CHANNEL",
    "REQUEST_TTL_MINUTES_DEFAULT",
    "REQUEST_TTL_MINUTES_MAX",
    "ROUTER_PREFIX",
    "SERVER_PATH_ENABLED_DEFAULT",
    "TOKEN_BYTES",
    "TOKEN_HASH_LEN",
    "UPLOAD_ROUTE",
    "WORKSPACE_MAX",
]
