"""The set of ENV keys edited by the settings page.

This defines the form's fields (what to show, how to input it, when to show it), NOT a
restriction: it is a local application, and the user knows what they are changing. Values
are written to ``.env`` as is; changes take effect on restart (Config is read at startup).

``visible_when`` is a visibility condition: the field is shown only when the CURRENT value of
another key equals the given one (computed reactively on the frontend from the form's
selection). That is how the postgres fields are hidden under ``DB_PROVIDER=sqlite`` and vice
versa.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class VisibleWhen:
    """The field is visible when the form's value of ``key`` equals ``equals``."""

    key: str
    equals: str


@dataclass(frozen=True)
class SetupField:
    """One editable field: ENV key + group code + English label/description + how to input it.

    The label and description are English fallback text: the form shows the translation from
    its own dictionary by the field key (``setup.field.<KEY>``), and these strings only when
    there is no translation. They also go into ``.env`` as a comment.
    """

    key: str
    group: str
    type: str  # "str" | "int" | "bool" | "choice"
    label: str
    description: str = ""
    choices: tuple[str, ...] = field(default=())
    secret: bool = False
    visible_when: VisibleWhen | None = None


_POSTGRES = VisibleWhen("DB_PROVIDER", "postgres")
_SQLITE = VisibleWhen("DB_PROVIDER", "sqlite")
# The form keeps a bool as the string the switch writes back (`String(true)`).
_DEV_MODE = VisibleWhen("APP_DEV_MODE", "true")

# A group code is the key of its label in the form's dictionary (``setup.group.<code>``); the
# label here is the fallback.
_APP = "app"
_DB = "database"
_SERVER = "server"
_WORKER = "worker"

GROUP_LABELS: dict[str, str] = {
    _APP: "Application",
    _DB: "Database",
    _SERVER: "Server",
    _WORKER: "Background jobs",
}

# The code lines the project maintains: the stable installation follows `main`, the working one
# follows `dev`. The list is closed not out of distrust but because the branch goes into git's
# arguments: free input here is a typo discovered only after the installation has stopped.
UPDATE_BRANCHES = ("main", "dev")

FIELDS: tuple[SetupField, ...] = (
    SetupField(
        "UPDATE_BRANCH", _APP, "choice", "Update branch",
        "Branch the installation updates to (origin/<branch>); the update fast-forwards "
        "and refuses to run if the checkout is on another branch",
        choices=UPDATE_BRANCHES,
    ),
    SetupField(
        "APP_DEV_MODE", _APP, "bool", "Developer mode",
        "Development tools and diagnostics in the interface",
    ),
    SetupField(
        "DB_PROVIDER", _DB, "choice", "Database provider",
        "postgres — an external server (full-featured); sqlite — a local file, nothing to install",
        choices=("postgres", "sqlite"),
    ),
    SetupField(
        "DB_PATH", _DB, "str", "SQLite file",
        "Path to the database file; empty — runtime/<profile>/app.sqlite3",
        visible_when=_SQLITE,
    ),
    SetupField(
        "DB_HOST", _DB, "str", "Database host",
        "PostgreSQL server address", visible_when=_POSTGRES,
    ),
    SetupField(
        "DB_PORT", _DB, "int", "Database port",
        "PostgreSQL port (usually 5432)", visible_when=_POSTGRES,
    ),
    SetupField(
        "DB_NAME", _DB, "str", "Database name",
        "Name of the database", visible_when=_POSTGRES,
    ),
    SetupField(
        "DB_USER", _DB, "str", "Database user",
        "PostgreSQL user name", visible_when=_POSTGRES,
    ),
    SetupField(
        "DB_PASSWORD", _DB, "str", "Database password",
        "PostgreSQL user password", secret=True, visible_when=_POSTGRES,
    ),
    SetupField(
        "DB_SSL", _DB, "bool", "Database TLS",
        "Encrypted connection with certificate verification (verify-full)",
        visible_when=_POSTGRES,
    ),
    SetupField(
        "SERVER_HOST", _SERVER, "str", "Server host",
        "Address the backend listens on (127.0.0.1 — local only)",
    ),
    SetupField(
        "SERVER_PORT", _SERVER, "int", "Server port",
        "HTTP server port (the app opens on it)",
    ),
    SetupField(
        "SERVER_VITE_PORT", _SERVER, "int", "Vite port (development)",
        "Frontend dev server port; needed only for local development",
        visible_when=_DEV_MODE,
    ),
    SetupField(
        "WORKER_ENABLED", _WORKER, "bool", "Background jobs",
        "Run the scheduler and job execution in this same process",
    ),
    SetupField(
        "WORKER_TICK_SECONDS", _WORKER, "int", "Scheduler interval, s",
        "How often to check the job queue",
    ),
    SetupField(
        "WORKER_MAX_CONCURRENT_RUNS", _WORKER, "int", "Concurrent jobs",
        "Maximum number of jobs running at once",
    ),
)

FIELD_BY_KEY: dict[str, SetupField] = {f.key: f for f in FIELDS}


__all__ = ["FIELDS", "FIELD_BY_KEY", "GROUP_LABELS", "SetupField", "VisibleWhen"]
