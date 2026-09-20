"""Активное рабочее пространство сессии агента: чьё оно и где лежит.

**Почему это вообще отдельный слой.** MCP-клиент спавнит шим, шим проксирует вызовы на общий
backend, и backend смонтирован ``stateless_http`` — сессий он не ведёт, а обслуживает сразу все
подключения и браузер. Поэтому «активное пространство» нельзя держать ни в переменной процесса
(она одна на всех, и соседняя сессия её затрёт), ни в сессии MCP (её тут нет). Единственное, чем
одно подключение отличается от другого, — заголовок, который шим себе выдумал при старте
(``core/mcp_headers``).

**Где лежит привязка.** В ``core_modules_state`` под ключом сессии — то есть в базе, а не в
памяти. Шим переживает перезапуск backend (это разные процессы), и привязка в памяти исчезла бы
посреди работы: агент, час назад выбравший пространство, внезапно получил бы «не выбрано». Строки
дешевле любой таблицы: хранилище уже есть, миграции не нужно.

**Три уровня разрешения**, от сильного к слабому: привязка этой сессии → пространство из конфига
запуска (заголовок-умолчание) → отказ. Поэтому проект со своим ``.mcp.json`` стартует уже
привязанным, а ``workspace_use`` перекрывает конфиг только для своей сессии и файла не трогает.

**Вызов без HTTP** (in-memory ``Client`` в тестах, прямой вызов из кода) заголовков не имеет
вовсе. Такой вызов получает один общий ключ ``_LOCAL_SESSION`` — не ошибку: отсутствие HTTP это
не сломанный клиент, а другой способ звать. Живой заголовок всегда сильнее этого ключа, и ровно
это проверяет тест поверх смонтированного сервера.
"""

from __future__ import annotations

from datetime import timedelta

from src.core.module_state import module_store
from src.core.utils.date import utc_now
from src.modules.workspace.codes import bare_code
from src.modules.workspace.constants import WORKSPACE_CODE_PREFIX
from src.modules.workspace.crud import workspace as workspace_crud
from src.modules.workspace.mcp.errors import no_active_workspace
from src.modules.workspace.models.workspace import Workspace

_STORE = module_store("workspace")

# Префикс ключа в общем хранилище модуля: там же лежит и всё остальное состояние
# ``workspace``, и без него привязки сессий смешались бы с ним в одном пространстве имён.
_KEY_PREFIX = "mcp_session:"

# Ключ вызова, пришедшего не по HTTP. Имя намеренно говорящее: увидев его в базе, читатель
# поймёт, что это не чья-то сессия, а общий ящик для вызовов без заголовка.
_LOCAL_SESSION = "local"

# Сколько живёт брошенная привязка. Сессии агента исчисляются часами, так что месяц — это
# «никогда не мешает»; уборка нужна только чтобы таблица не росла вечно от каждого запуска.
_TTL = timedelta(days=30)


def _headers() -> dict[str, str]:
    """Заголовки текущего HTTP-запроса; вне запроса — пусто, без исключения.

    Импорт ``fastmcp`` — в теле функции: модуль тянется и туда, где форка быть не должно.
    """
    from fastmcp.server.dependencies import get_http_headers

    return get_http_headers()


def session_id() -> str:
    """Ключ сессии: идентификатор из заголовка, иначе общий локальный ящик."""
    from src.core.mcp_headers import MCP_SESSION_HEADER

    return _headers().get(MCP_SESSION_HEADER) or _LOCAL_SESSION


def _default_code() -> str | None:
    """Пространство из конфига запуска (заголовок-умолчание), уже голым кодом.

    Чужой префикс здесь не отказ, а игнор: значение приходит из файла настроек пользователя, и
    ронять весь сервер из-за опечатки в нём означало бы сделать необязательную настройку
    обязательной. Отсутствие умолчания агент увидит обычным «пространство не выбрано».
    """
    from src.core.mcp_headers import MCP_WORKSPACE_HEADER

    raw = _headers().get(MCP_WORKSPACE_HEADER)
    if not raw:
        return None
    try:
        return bare_code(raw, WORKSPACE_CODE_PREFIX)
    except ValueError:
        return None


async def bound_code() -> str | None:
    """Код пространства, привязанного к этой сессии (без учёта умолчания)."""
    row = await _STORE.get(_KEY_PREFIX + session_id())
    return row.get("workspace") if isinstance(row, dict) else None


async def active_code() -> str | None:
    """Голый код активного пространства: привязка сессии, иначе умолчание, иначе ``None``."""
    return await bound_code() or _default_code()


async def bind(workspace_code: str) -> None:
    """Привязать сессию к пространству. Время — чтобы брошенные привязки было чем убирать."""
    await _STORE.set(
        _KEY_PREFIX + session_id(),
        {"workspace": workspace_code, "at": utc_now().isoformat()},
    )


async def require_active() -> Workspace:
    """Активное пространство строкой или отказ с путём починки.

    Пространство читается из базы, а не берётся кодом на веру: привязку могли поставить неделю
    назад, а пространство с тех пор — удалить. Удалённое тоже отдаём: его задачи никуда не
    делись, и «не найдено» на живых данных было бы враньём. Пропало совсем — это то же «выбери
    пространство», потому что чинится тем же.
    """
    code = await active_code()
    row = (
        await workspace_crud.workspace_get(code, include_deleted=True) if code else None
    )
    if row is None:
        raise no_active_workspace()
    return row


async def prune() -> int:
    """Снести привязки старше ``_TTL``; вернуть, сколько снесли.

    Зовётся при привязке, а не по расписанию: уборка нужна редко, а лишняя задача планировщика
    ради десятка строк — это орган, который нечем кормить.
    """
    edge = utc_now() - _TTL
    stale = [
        key
        for key, value in (await _STORE.all()).items()
        if key.startswith(_KEY_PREFIX)
        and isinstance(value, dict)
        and str(value.get("at", "")) < edge.isoformat()
    ]
    for key in stale:
        await _STORE.delete(key)
    return len(stale)


__all__ = [
    "active_code",
    "bind",
    "bound_code",
    "prune",
    "require_active",
    "session_id",
]
