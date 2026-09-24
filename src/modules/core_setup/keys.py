"""Набор ENV-ключей, редактируемых страницей настроек.

Это определение полей формы (что показывать, как вводить, когда показывать), а НЕ
запрет: локальное приложение, пользователь сам знает, что меняет. Значения пишутся в
``.env`` как есть, изменения применяются рестартом (Config читается на старте).

``visible_when`` — условие видимости: поле показывается, только когда ТЕКУЩЕЕ значение
другого ключа равно заданному (вычисляется на фронте реактивно от выбора в форме).
Так postgres-поля скрыты при ``DB_PROVIDER=sqlite`` и наоборот.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class VisibleWhen:
    """Поле видно, когда значение ``key`` в форме равно ``equals``."""

    key: str
    equals: str


@dataclass(frozen=True)
class SetupField:
    """Одно редактируемое поле: ENV-ключ + код группы + английские название/описание + как вводить.

    Название и описание — английский запасной текст: форма показывает перевод из своего словаря
    по ключу поля (``setup.field.<KEY>``), а эти строки — когда перевода нет. Они же уходят
    комментарием в ``.env``.
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

# Код группы — ключ её подписи в словаре формы (``setup.group.<код>``); подпись здесь — запасная.
_DB = "database"
_SERVER = "server"
_WORKER = "worker"
_UPDATE = "update"

GROUP_LABELS: dict[str, str] = {
    _DB: "Database",
    _SERVER: "Server",
    _WORKER: "Background jobs",
    _UPDATE: "Update",
}

# Линии кода, которые ведёт проект: stable-установка следует за `main`, рабочая — за `dev`.
# Список закрытый не из недоверия, а потому что ветка идёт в аргументы git: свободный ввод здесь
# — это опечатка, которая выясняется уже после остановки установки.
UPDATE_BRANCHES = ("main", "dev")

FIELDS: tuple[SetupField, ...] = (
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
    SetupField(
        "UPDATE_BRANCH", _UPDATE, "choice", "Update branch",
        "Branch the installation updates to (origin/<branch>); the update fast-forwards "
        "and refuses to run if the checkout is on another branch",
        choices=UPDATE_BRANCHES,
    ),
)

FIELD_BY_KEY: dict[str, SetupField] = {f.key: f for f in FIELDS}


__all__ = ["FIELDS", "FIELD_BY_KEY", "GROUP_LABELS", "SetupField", "VisibleWhen"]
