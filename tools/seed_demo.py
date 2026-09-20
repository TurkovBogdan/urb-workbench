"""Сидер демо-данных модуля ``tasks``: пространства, группы, задачи, этапы и журнал.

Нужен для отладки интерфейса: пустой список ничего не проверяет, а руками набивать три десятка
задач с этапами и журналом — полчаса на каждый прогон. Скрипт кладёт связный срез, где встречается
каждое значение справочника и каждое состояние, которое интерфейс обязан уметь показать.

**Пишет в базу из ``.env``** — ту же, что видит приложение (``Config()`` читает провайдера и путь
оттуда). Пишет ТОЛЬКО вставками: ни ``DROP``, ни ``TRUNCATE``, ни ``DELETE`` здесь нет и быть не
должно — снести демо-пространство можно из интерфейса, а массовые удаления из скрипта необратимы.

Данные заводятся через CRUD модуля, а не прямыми ``INSERT``: путь тот же, которым ходит
приложение, поэтому строка, которую бэк бы не принял, не появится и здесь. Побочная выгода — отметки
фаз (``started_at`` и соседи) проставляет сама смена статуса, а не мы руками.

Каждый прогон добавляет НОВЫЙ набор: коды случайны, и второй запуск даёт вторые пространства с тем
же составом. Так и задумано — сравнивать два среза проще, чем угадывать, что изменилось в одном.

    uv run python tools/seed_demo.py           # три пространства с полным составом
    uv run python tools/seed_demo.py --small   # одно пространство, без веток и корзины
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.core.config import Config
from src.core.database import close_database, init_database
from src.core.utils.date import utc_now
from src.modules.tasks.constants import (
    ACTOR_AGENT,
    NOTE_DECISION,
    NOTE_FACT,
    NOTE_FINDING,
    NOTE_REMARK,
    PRIORITY_BURNING,
    PRIORITY_FROZEN,
    PRIORITY_HIGH,
    PRIORITY_LOW,
    PRIORITY_NORMAL,
    STATUS_BACKLOG,
    STATUS_CANCELED,
    STATUS_DONE,
    STATUS_IN_PROGRESS,
    STATUS_IN_REVIEW,
    STATUS_IN_TEST,
    STATUS_PLANNED,
    TYPE_EXTENDED,
    TYPE_SIMPLE,
    TYPE_STANDARD,
)
from src.modules.tasks.crud import group as group_crud
from src.modules.tasks.crud import link as link_crud
from src.modules.tasks.crud import note as note_crud
from src.modules.tasks.crud import stage as stage_crud
from src.modules.tasks.crud import task as task_crud
from src.modules.workspace.crud import workspace as workspace_crud

MARK = "демо-данные"
"""Метка в описании пространства: по ней человек отличает наведённое от своего."""


# ── что заводим ───────────────────────────────────────────────────────────────
# Состав описан данными, а не кодом: добавить задачу — строка в списке, а не ветка в функции.

WORKSPACES = [
    {
        "title": "Демо: разработка",
        "description": f"Рабочее пространство продуктовой команды ({MARK})",
        "color": "indigo",
        "icon": "code",
        "groups": [
            {"title": "Биллинг", "description": "Тарифы, счета, платежи", "color": "amber", "icon": "wallet"},
            {"title": "Интерфейс", "description": "Экраны, формы, вёрстка", "color": "sky", "icon": "layout"},
            {"title": "Инфраструктура", "description": "Сборка, деплой, мониторинг", "color": "slate", "icon": "server"},
            # Группа НАМЕРЕННО без задач: список показывает такие приглушёнными внизу, и они же
            # служат целью перетаскивания. Без пустой группы в данных этот случай не увидеть.
            {"title": "Документация", "description": "Тексты, README, справка", "color": "teal", "icon": "notebook"},
        ],
    },
    {
        "title": "Демо: личное",
        "description": f"Дела вне работы ({MARK})",
        "color": "green",
        "icon": "home",
        "groups": [
            {"title": "Здоровье", "description": "Врачи, спорт, режим", "color": "rose", "icon": "heart"},
            {"title": "Дом", "description": "Быт и ремонт", "color": "orange", "icon": "tool"},
        ],
    },
    {
        "title": "Демо: заказчик",
        "description": f"Внешний проект с приёмкой ({MARK})",
        "color": "violet",
        "icon": "briefcase",
        "groups": [
            {"title": "Интеграция", "description": "Обмен данными с их системой", "color": "cyan", "icon": "plug"},
        ],
    },
]

# Задачи первого пространства — самый плотный срез: все три типа, все статусы, ветка с подзадачами,
# удалённая строка и задача без группы.
DEV_TASKS = [
    {
        "title": "Перенести тарифы на новую схему",
        "description": "Тарифы считаются по новой таблице, старая колонка не читается нигде",
        "group": "Биллинг",
        "type": TYPE_EXTENDED,
        "status": STATUS_IN_PROGRESS,
        "priority": PRIORITY_BURNING,
        "deadline_days": 3,
        "context": (
            "Схема описана в `docs/billing/pricing.md`. Старое поле `plan_code` читают три модуля, "
            "список — в задаче TASK@ниже.\n\n"
            "Эталон переноса — миграция `bil_004`, там же приём с двойной записью."
        ),
        "constraints": (
            "- можно: менять код биллинга и его миграции\n"
            "- спросить: любое изменение публичного API\n"
            "- нельзя: трогать модуль `workspace` и чужие таблицы"
        ),
        "criteria": (
            "1. `pytest tests/modules/billing -q` зелёный\n"
            "2. Старая колонка не читается: grep по `plan_code` пуст\n"
            "3. Миграция откатывается и накатывается на копии боевой базы"
        ),
        "body": (
            "Иду по слоям снизу вверх: миграция → модели → CRUD → API → фронт.\n\n"
            "Прочитал: `models/pricing.py`, `crud/pricing.py`, `api.py`, миграции `bil_001…004`.\n"
            "Трону: те же файлы плюс `web/src/features/billing/api.ts`."
        ),
        "stages": [
            {"title": "Миграция и модели", "description": "Новая таблица и перенос значений", "status": STATUS_DONE,
             "evidence": "tsm-style миграция bil_005; pytest tests/modules/billing/test_migrations.py → 4 passed"},
            {"title": "CRUD и API", "description": "Чтение через новую таблицу", "status": STATUS_IN_PROGRESS,
             "body": "Ломается сериализация старого поля в ответе списка — разбираюсь."},
            {"title": "Фронт и снос колонки", "description": "Правка клиента и удаление legacy", "status": STATUS_PLANNED},
        ],
        "notes": [
            {"type": NOTE_DECISION, "title": "Двойная запись на время переноса",
             "body": "Пишем в обе таблицы, читаем из новой. Иначе откат теряет платежи за сутки.",
             "resolution": "Проверено на копии базы: расхождений нет"},
            {"type": NOTE_DECISION, "title": "Что делать со старыми счетами до 2024 года",
             "body": "Переносить их или оставить в архивной таблице? Ответа нет — пока не переношу."},
            {"type": NOTE_FACT, "title": "Строк в pricing_plan: 1842", "body": "Из них живых 61",
             "resolution": "записано"},
            {"type": NOTE_FINDING, "title": "В `crud/invoice.py` N+1 на списке счетов",
             "body": "Каждая строка тянет тариф отдельным запросом. К задаче не относится."},
        ],
        "children": [
            {"title": "Обновить клиент биллинга", "type": TYPE_STANDARD, "status": STATUS_PLANNED,
             "priority": PRIORITY_HIGH, "description": "Фронт читает новое поле"},
            {"title": "Снести legacy-колонку", "type": TYPE_SIMPLE, "status": STATUS_BACKLOG,
             "priority": PRIORITY_LOW, "description": "После того, как всё переедет"},
        ],
    },
    {
        "title": "Форма счёта не сохраняет комментарий",
        "description": "Комментарий доезжает до бэка и сохраняется",
        "group": "Биллинг",
        # Этапы есть только у расширенной — на стандартной этот же набор отказал бы в CRUD.
        "type": TYPE_EXTENDED,
        "status": STATUS_IN_REVIEW,
        "priority": PRIORITY_HIGH,
        "deadline_days": 1,
        "context": "Воспроизводится на форме счёта: поле заполнено, после сохранения пустое.",
        "criteria": "1. Комментарий виден после перезагрузки страницы\n2. Тест на регресс",
        "body": "Похоже на полную замену карточки без поля: форма не шлёт `comment`.",
        "stages": [
            {"title": "Воспроизвести", "description": "Найти, где теряется", "status": STATUS_DONE,
             "evidence": "DevTools: в теле PUT нет ключа comment"},
            {"title": "Починить и закрыть тестом", "status": STATUS_DONE,
             "evidence": "pytest tests/modules/billing/test_api_invoice.py -q → 12 passed"},
        ],
        "notes": [
            {"type": NOTE_REMARK, "title": "Проверь ещё форму правки, не только создания",
             "body": "От постановщика, по ходу работы.", "resolution": "Проверил, там та же ошибка — починил обе"},
        ],
    },
    {
        "title": "Тёмная тема: карточки теряют границу",
        "description": "Граница карточки видна в обеих темах",
        "group": "Интерфейс",
        "type": TYPE_EXTENDED,
        "status": STATUS_IN_TEST,
        "priority": PRIORITY_NORMAL,
        "context": "Токен `--border` в тёмной теме совпадает с фоном.",
        "constraints": "- нельзя: менять палитру целиком, правим только токен границы",
        "criteria": "1. Скриншот обеих тем\n2. Контраст не ниже 1.5:1",
        "body": "Меняю токен и прохожу по всем местам, где он используется.",
        "stages": [
            {"title": "Правка токена", "status": STATUS_DONE, "evidence": "web/src/styles/tokens.css:41"},
            {"title": "Обход экранов", "description": "Задачи, группы, пространства, ресёрч", "status": STATUS_IN_PROGRESS},
        ],
        "notes": [
            {"type": NOTE_FACT, "title": "Контраст был 1.02:1", "body": "Замер в DevTools", "resolution": "записано"},
        ],
    },
    {
        "title": "Список задач: секции по группам",
        "description": "Задачи разложены по группам, «Без группы» — последней",
        "group": "Интерфейс",
        "type": TYPE_STANDARD,
        "status": STATUS_DONE,
        "priority": PRIORITY_NORMAL,
        "context": "Раскладку считает стор, страница только рисует.",
        "criteria": "1. Пустые группы стоят внизу приглушёнными\n2. «Без группы» стоит последней",
        # Этапов здесь нет намеренно: это образец СТАНДАРТНОЙ задачи, у которой план живёт прозой.
        # Без такого примера демо показывало бы только расширенные, и разница между уровнями
        # оставалась бы словами в справке.
        "body": "Группировка в computed, порядок задаёт бэк. Тронул stores/tasks.store.ts "
                "(sections) и components/TaskListTable.vue.",
        "notes": [
            {"type": NOTE_DECISION, "title": "Секцию «Без группы» ставим последней",
             "body": "Это остаток, а не тема наравне с остальными.", "resolution": "Согласовано с постановщиком"},
        ],
    },
    {
        "title": "Поднять Python до 3.13",
        "description": "Сборка и тесты идут на 3.13",
        "group": "Инфраструктура",
        "type": TYPE_EXTENDED,
        "status": STATUS_BACKLOG,
        "priority": PRIORITY_LOW,
        "context": "Зависимости проверены наполовину: `greenlet` и `asyncpg` под вопросом.",
        "constraints": "- спросить: обновление зависимостей с ломающими изменениями",
        "criteria": "1. Весь прогон тестов зелёный на 3.13\n2. Сборка фронта не затронута",
        "body": "Сначала прогон на ветке, потом обновление окружения установки.",
        "notes": [
            {"type": NOTE_DECISION, "title": "Ждём релиз asyncpg с поддержкой 3.13",
             "body": "Иначе придётся собирать из исходников."},
        ],
    },
    {
        "title": "Заморожено: переезд на Postgres в проде",
        "description": "Прод работает на Postgres",
        "group": "Инфраструктура",
        "type": TYPE_STANDARD,
        "status": STATUS_PLANNED,
        "priority": PRIORITY_FROZEN,
        "context": "Решение отложено до конца квартала.",
        "body": "План есть, сроков нет.",
    },
    {
        "title": "Разобрать входящие идеи",
        "description": "Список идей разобран, лишнее закрыто",
        "group": None,
        "type": TYPE_SIMPLE,
        "status": STATUS_BACKLOG,
        "priority": PRIORITY_NORMAL,
        "context": "Задача вне групп — проверяет секцию «Без группы».",
    },
    {
        "title": "Отменённая затея с плагинами",
        "description": "Плагины сторонних разработчиков",
        "group": "Инфраструктура",
        "type": TYPE_STANDARD,
        "status": STATUS_CANCELED,
        "priority": PRIORITY_LOW,
        "context": "Закрыто: инструмент на одного разработчика, плагины некому писать.",
    },
    {
        "title": "Удалённая задача с прошлого спринта",
        "description": "Лежит в корзине — проверяет тумблер «показывать удалённые»",
        "group": "Биллинг",
        "type": TYPE_SIMPLE,
        "status": STATUS_BACKLOG,
        "priority": PRIORITY_NORMAL,
        "deleted": True,
    },
]

PERSONAL_TASKS = [
    {
        "title": "Записаться к стоматологу",
        "description": "Приём назначен",
        "group": "Здоровье",
        "type": TYPE_SIMPLE,
        "status": STATUS_PLANNED,
        "priority": PRIORITY_HIGH,
        "deadline_days": 5,
    },
    {
        "title": "Разобрать кладовку",
        "description": "Кладовка разобрана, лишнее вынесено",
        "group": "Дом",
        "type": TYPE_SIMPLE,
        "status": STATUS_BACKLOG,
        "priority": PRIORITY_LOW,
    },
    {
        "title": "Собрать полку в кабинете",
        "description": "Полка стоит и держит книги",
        "group": "Дом",
        "type": TYPE_SIMPLE,
        "status": STATUS_DONE,
        "priority": PRIORITY_NORMAL,
        "deadline_days": -2,
    },
]

CLIENT_TASKS = [
    {
        "title": "Обмен заказами через их API",
        "description": "Заказы приходят и подтверждаются автоматически",
        "group": "Интеграция",
        "type": TYPE_EXTENDED,
        "status": STATUS_IN_PROGRESS,
        "priority": PRIORITY_HIGH,
        "deadline_days": 10,
        "context": (
            "Документация их API — в приложении к договору, версия 2.3.\n"
            "Тестовый контур отвечает медленно: до 8 секунд на запрос."
        ),
        "constraints": (
            "- можно: заводить свои таблицы под очередь обмена\n"
            "- спросить: любые изменения в договорном формате\n"
            "- нельзя: писать в их боевой контур с нашей машины"
        ),
        "criteria": (
            "1. Заказ из их тестового контура доезжает и подтверждается\n"
            "2. Повторная доставка того же заказа не создаёт дубль\n"
            "3. Отказ их стороны виден в журнале задачи, а не только в логах"
        ),
        "body": "Очередь на нашей стороне, ретраи с экспоненциальной задержкой, идемпотентность по их id.",
        "stages": [
            {"title": "Клиент их API", "status": STATUS_DONE, "evidence": "src/modules/exchange/client.py; 9 тестов зелёные"},
            {"title": "Очередь и ретраи", "status": STATUS_IN_PROGRESS, "body": "Ретраи готовы, идемпотентность в работе."},
            {"title": "Приёмка на их контуре", "status": STATUS_PLANNED, "description": "Совместный прогон с их инженером"},
            {"title": "Брошенный заход через вебхуки", "status": STATUS_CANCELED,
             "description": "Их сторона вебхуки не отдаёт — отказались"},
        ],
        "notes": [
            {"type": NOTE_REMARK, "title": "Сроки двигать нельзя, приёмка 30-го",
             "body": "От заказчика на созвоне."},
            {"type": NOTE_DECISION, "title": "Идемпотентность по их order_id, а не по нашему",
             "body": "Их id стабилен между повторами, наш генерируется на вставке.",
             "resolution": "Проверено: повтор не создаёт дубль"},
            {"type": NOTE_FINDING, "title": "Их тестовый контур отдаёт 500 на пустой список",
             "body": "Не наша зона, но об этом стоит сказать их команде."},
            {"type": NOTE_FACT, "title": "Таймаут их API — 8 с на запрос",
             "body": "Замер по 50 запросам, медиана 3.1 с", "resolution": "записано"},
        ],
    },
    {
        "title": "Отчёт по интеграции для заказчика",
        "description": "Отчёт отправлен и принят",
        "group": "Интеграция",
        "type": TYPE_STANDARD,
        "status": STATUS_IN_REVIEW,
        "priority": PRIORITY_NORMAL,
        "deadline_days": 2,
        "criteria": "1. Отчёт покрывает все три этапа\n2. Приложены номера прогонов",
        "body": "Собираю из журнала задачи выше.",
    },
]


# ── сборка ────────────────────────────────────────────────────────────────────


async def seed_task(*, workspace_code: str, spec: dict, groups: dict[str, str], parent_code: str | None = None) -> str:
    """Завести задачу со всем её содержимым и вернуть код."""
    deadline = None
    if spec.get("deadline_days") is not None:
        deadline = utc_now() + timedelta(days=spec["deadline_days"])

    task = await task_crud.task_create(
        workspace_code=workspace_code,
        title=spec["title"],
        description=spec.get("description", ""),
        context=spec.get("context", ""),
        constraints=spec.get("constraints", ""),
        criteria=spec.get("criteria", ""),
        body=spec.get("body", ""),
        type=spec.get("type", TYPE_SIMPLE),
        priority=spec.get("priority", PRIORITY_NORMAL),
        group_code=groups.get(spec["group"]) if spec.get("group") else None,
        parent_code=parent_code,
        created_by=spec.get("created_by", ACTOR_AGENT if spec.get("type") != TYPE_SIMPLE else "human"),
        deadline_at=deadline,
    )

    # Статус ставим отдельно: только этот путь проставляет отметки фаз, и демо-данные должны
    # выглядеть так же, как настоящие, — с датой начала у всего, что уже в работе.
    status = spec.get("status", STATUS_BACKLOG)
    if status != STATUS_BACKLOG:
        await task_crud.task_update_status(task.code, status)

    for stage_spec in spec.get("stages", []):
        stage = await stage_crud.stage_create(
            task_code=task.code,
            title=stage_spec["title"],
            description=stage_spec.get("description", ""),
            body=stage_spec.get("body", ""),
        )
        if stage_spec.get("evidence"):
            await stage_crud.stage_update(stage.code, evidence=stage_spec["evidence"])
        stage_status = stage_spec.get("status", STATUS_PLANNED)
        if stage_status != STATUS_PLANNED:
            # Закрытый этап проходит через работу: иначе у него не будет отметки начала.
            if stage_status in (STATUS_DONE, STATUS_IN_REVIEW, STATUS_IN_TEST):
                await stage_crud.stage_update_status(stage.code, STATUS_IN_PROGRESS)
            await stage_crud.stage_update_status(stage.code, stage_status)

    for note_spec in spec.get("notes", []):
        await note_crud.note_create(
            task_code=task.code,
            type=note_spec["type"],
            title=note_spec["title"],
            body=note_spec.get("body", ""),
            resolution=note_spec.get("resolution", "") if note_spec["type"] == NOTE_FACT else "",
        )
        if note_spec.get("resolution") and note_spec["type"] != NOTE_FACT:
            entries = await note_crud.note_list_by_task(task.code)
            await note_crud.note_resolve(entries[-1].code, note_spec["resolution"])

    for child in spec.get("children", []):
        await seed_task(workspace_code=workspace_code, spec=child, groups=groups, parent_code=task.code)

    if spec.get("deleted"):
        await task_crud.task_delete(task.code)

    return task.code


async def seed_workspace(spec: dict, tasks: list[dict]) -> dict:
    """Пространство целиком: карточка, группы, задачи. Возвращает счётчики для отчёта."""
    workspace = await workspace_crud.workspace_create(
        title=spec["title"],
        description=spec["description"],
        color=spec["color"],
        icon=spec["icon"],
    )
    groups: dict[str, str] = {}
    for index, group_spec in enumerate(spec["groups"]):
        group = await group_crud.group_create(
            workspace_code=workspace.code,
            title=group_spec["title"],
            description=group_spec["description"],
            color=group_spec["color"],
            icon=group_spec["icon"],
            # Первая группа выше: порядок задаёт больший `sort`, и одинаковые значения дали бы
            # алфавит вместо задуманной раскладки.
            sort=500 + (len(spec["groups"]) - index) * 10,
        )
        groups[group_spec["title"]] = group.code

    for task_spec in tasks:
        await seed_task(workspace_code=workspace.code, spec=task_spec, groups=groups)

    rows = await task_crud.task_list_by_workspace(workspace.code, include_deleted=True)
    return {"workspace": workspace.title, "code": workspace.code, "groups": len(groups), "tasks": len(rows)}


async def main(small: bool) -> int:
    config = Config()
    target = config.db_path or config.db_name or "по умолчанию"
    print(f"база: {config.db_provider} → {target}")

    plan = [(WORKSPACES[0], DEV_TASKS)]
    if not small:
        plan += [(WORKSPACES[1], PERSONAL_TASKS), (WORKSPACES[2], CLIENT_TASKS)]

    await init_database(config)
    try:
        report = [await seed_workspace(spec, tasks) for spec, tasks in plan]
    finally:
        await close_database()

    print("\nзаведено:")
    for row in report:
        print(f"  {row['workspace']} ({row['code']}): групп {row['groups']}, задач {row['tasks']}")
    print("\nснести демо можно из интерфейса: «Пространства» → удалить → «Удалить навсегда».")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Демо-данные модуля tasks: пространства, группы, задачи.")
    parser.add_argument("--small", action="store_true", help="только одно пространство разработки")
    args = parser.parse_args()
    raise SystemExit(asyncio.run(main(args.small)))
