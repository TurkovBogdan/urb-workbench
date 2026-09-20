"""Константы модуля ``tasks`` — длина кода, префиксы, размеры полей и справочники значений.

Единый источник для трёх мест, которые обязаны совпадать: ORM-модель (``String(n)`` +
``CheckConstraint``), миграция (``sa.CheckConstraint``) и усечение в CRUD (``text.clip``).
Разъехались бы они — расхождение всплыло бы только на PostgreSQL: SQLite ширину ``VARCHAR``
не проверяет вовсе.

Справочники (``TASK_STATUSES`` и соседи) — **кортежи строк, а не нативный enum БД**. Причина
ровно одна: миграции катятся и на SQLite (dev, zero-install), и на PostgreSQL, а ``CREATE TYPE``
на SQLite не существует. Побочная выгода — новое значение статуса добавляется правкой кортежа и
одного ``CHECK``, без ``ALTER TYPE`` и без переливки таблицы.

Лимиты текста едины на весь модуль: ``title`` и ``description`` — это строки, по которым человек
и агент просматривают список, а не текст (текст живёт в ``body`` без лимита).
"""

from __future__ import annotations

# ── presentation code prefixes (граница, НЕ хранилище — см. tasks.codes) ──
# В базе лежит голый hex-код; тип-слово надевается на выходе и снимается на входе.
# Префикса пространства здесь нет: сущность принадлежит модулю ``workspace``, и тип-слово к ней
# берётся оттуда (``workspace.constants.WORKSPACE_CODE_PREFIX``). Своя копия разошлась бы с
# оригиналом ровно в тот день, когда владелец своё слово переименует.
GROUP_CODE_PREFIX = "GROUP"
TASK_CODE_PREFIX = "TASK"
STAGE_CODE_PREFIX = "STAGE"
NOTE_CODE_PREFIX = "NOTE"

# Длина кода сущности в hex-символах. Код агент перепечатывает в каждый вызов и платит за него
# токенами: 10 знаков вместо 22 экономят ~6.8 токена на ссылку. Короче нельзя — на 8 знаках
# опечатка в один символ попадает в живую строку раз на 3600, на 10 — раз на 733000.
# Совпадает с ``workspace.constants.CODE_LEN``: код пространства лежит в наших колонках, и
# разная ширина под один код — это будущая усечённая ссылка.
CODE_LEN = 10

# ── размеры текстовых колонок ──
# Триада одинакова у всех сущностей модуля: ``title`` — название, ``description`` — что это и
# зачем (по этим двум агент решает, читать ли дальше), ``body`` — тело в markdown.
TITLE_MAX = 128
DESCRIPTION_MAX = 512
BODY_MAX = 8192
COLOR_MAX = 32
ICON_MAX = 64
# Постановка задачи: детали, границы и требования к сдаче. Пишет человек.
CONTEXT_MAX = 4048
CONSTRAINTS_MAX = 1024
CRITERIA_MAX = 1024
# Указатель на доказательство выполнения этапа. Тесен намеренно: вывод команды сюда не влезает,
# и писать в него рассказ вместо ссылки не выйдет.
EVIDENCE_MAX = 1024
# Журнал: предмет записи и её разрешение.
NOTE_BODY_MAX = 2048
RESOLUTION_MAX = 1024
# Ширина колонок, хранящих значение из справочника ниже (статус/приоритет/тип/актор). Самое
# длинное значение — ``in_progress`` (11), запас на одно-два будущих слова.
ENUM_VALUE_MAX = 16

# ── позиции в списке ──
# Больший ``sort`` = выше. Ненулевое стартовое значение, чтобы первую строку можно было двинуть
# и вверх, и вниз, не перенумеровывая соседей; шаг 5 оставляет место для четырёх вставок между
# любыми двумя соседями без переупорядочивания всего списка.
SORT_DEFAULT = 500
SORT_STEP = 5

# ── статусы ──
# Один справочник на задачу и на этап плана: два набора значений в одном модуле разъехались бы,
# и читателю пришлось бы держать в голове, какой где. Отличаются только умолчания.
STATUS_BACKLOG = "backlog"
STATUS_PLANNED = "planned"
STATUS_IN_PROGRESS = "in_progress"
STATUS_IN_TEST = "in_test"
STATUS_IN_REVIEW = "in_review"
STATUS_DONE = "done"
STATUS_CANCELED = "canceled"
TASK_STATUSES = (
    STATUS_BACKLOG,
    STATUS_PLANNED,
    STATUS_IN_PROGRESS,
    STATUS_IN_TEST,
    STATUS_IN_REVIEW,
    STATUS_DONE,
    STATUS_CANCELED,
)
TASK_STATUS_DEFAULT = STATUS_BACKLOG
# Этап заводят уже назначенным: он часть плана, а не идея на будущее, и очередь ему задаёт номер.
STAGE_STATUS_DEFAULT = STATUS_PLANNED
# Терминальные статусы: работа окончена (успехом или отказом) и обратно сама не поедет. Нужны
# там, где «активное» отделяется от истории, — и у задачи, и у этапа.
TASK_STATUSES_TERMINAL = (STATUS_DONE, STATUS_CANCELED)

# ── приоритеты задачи ──
PRIORITY_BURNING = "burning"
PRIORITY_HIGH = "high"
PRIORITY_NORMAL = "normal"
PRIORITY_LOW = "low"
PRIORITY_FROZEN = "frozen"
TASK_PRIORITIES = (
    PRIORITY_BURNING,
    PRIORITY_HIGH,
    PRIORITY_NORMAL,
    PRIORITY_LOW,
    PRIORITY_FROZEN,
)
TASK_PRIORITY_DEFAULT = PRIORITY_NORMAL
# Вес для сортировки: меньший вес = важнее (``ORDER BY weight ASC`` ставит горящее наверх).
# Сортировать по самому слову нельзя — алфавит про важность ничего не знает. Шаг 10 оставляет
# место новому приоритету между любыми двумя соседними.
TASK_PRIORITY_WEIGHTS = {
    PRIORITY_BURNING: 10,
    PRIORITY_HIGH: 20,
    PRIORITY_NORMAL: 30,
    PRIORITY_LOW: 40,
    PRIORITY_FROZEN: 50,
}

# ── тип задачи ──
# Глубина ведения, а не место в иерархии: контейнером задача становится от наличия детей.
# Три уровня, и каждый следующий добавляет ровно один способ вести работу:
#
#   simple    — заголовок и цель. Ни постановки, ни плана; часто это задача человеку.
#   standard  — постановка (контекст, границы, критерии), план прозой и журнал работы.
#   extended  — плюс ЭТАПЫ: работа разбита на шаги, каждый со своим состоянием и
#               доказательством выполнения.
#
# Граница между standard и extended проходит именно по этапам, а не по «плотности ведения»
# вообще: план прозой отвечает на вопрос «как я это сделаю», этапы — на «где я сейчас и чем
# доказано пройденное». Второй вопрос осмыслен только у работы, которая длится дольше одного
# захода, и навязывать его обычной задаче значит требовать церемонии там, где хватает абзаца.
TYPE_SIMPLE = "simple"
TYPE_STANDARD = "standard"
TYPE_EXTENDED = "extended"
TASK_TYPES = (TYPE_SIMPLE, TYPE_STANDARD, TYPE_EXTENDED)
TASK_TYPE_DEFAULT = TYPE_SIMPLE
# Типы с постановкой, планом и журналом — всё, кроме простой.
TASK_TYPES_WITH_PLAN = (TYPE_STANDARD, TYPE_EXTENDED)
# Типы с этапами — только расширенная. Отдельный кортеж, а не срез предыдущего: это два разных
# правила, и склеить их значит однажды сдвинуть оба, меняя одно.
TASK_TYPES_WITH_STAGES = (TYPE_EXTENDED,)

# ── тип записи журнала ──
# Что описывает строка. Порядок от частого к редкому: первое значение перечисления агент
# выбирает заметно чаще прочих, и частый вид должен стоять раньше редкого.
NOTE_DECISION = "decision"
NOTE_REMARK = "remark"
NOTE_FINDING = "finding"
NOTE_FACT = "fact"
NOTE_TYPES = (NOTE_DECISION, NOTE_REMARK, NOTE_FINDING, NOTE_FACT)
# Виды, которые вообще бывают открытыми. ``fact`` закрыт в момент записи — он ничего не ждёт.
NOTE_TYPES_OPENABLE = (NOTE_DECISION, NOTE_REMARK, NOTE_FINDING)
# Виды, незакрытость которых держит сдачу. Решение без разрешения — это допущение, и снять его
# обязан тот, кто его принял; замечание — просьба постановщика, и учесть её обязан исполнитель.
# Находка сюда НЕ входит: она про работу вне этой задачи, разбирает её человек в своём порядке,
# и посчитай мы её наравне — первая же находка заперла бы сдачу навсегда.
NOTE_TYPES_BLOCKING = (NOTE_DECISION, NOTE_REMARK)
# Виды, которые заводит агент. ``remark`` — слово постановщика, и инструмента с ним у агента
# нет: обе половины записи, написанные одной рукой, превращают шлюз в самооценку.
NOTE_TYPES_BY_AGENT = (NOTE_DECISION, NOTE_FINDING, NOTE_FACT)

# ── вид актора ──
# Кто завёл строку. Тот же словарь, что и у типа задачи, но смысл другой (авторство, а не
# адресат), поэтому кортеж отдельный: разъехаться им никто не мешает.
ACTOR_HUMAN = "human"
ACTOR_AGENT = "agent"
ACTOR_KINDS = (ACTOR_HUMAN, ACTOR_AGENT)
TASK_CREATED_BY_DEFAULT = ACTOR_HUMAN


def sql_in(values: tuple[str, ...]) -> str:
    """Кортеж значений → строка для ``col IN (...)`` в ``CheckConstraint``."""
    return ", ".join(f"'{value}'" for value in values)


__all__ = [
    "ACTOR_AGENT",
    "ACTOR_HUMAN",
    "ACTOR_KINDS",
    "BODY_MAX",
    "CODE_LEN",
    "COLOR_MAX",
    "CONSTRAINTS_MAX",
    "CONTEXT_MAX",
    "CRITERIA_MAX",
    "DESCRIPTION_MAX",
    "ENUM_VALUE_MAX",
    "EVIDENCE_MAX",
    "GROUP_CODE_PREFIX",
    "ICON_MAX",
    "NOTE_BODY_MAX",
    "NOTE_CODE_PREFIX",
    "NOTE_DECISION",
    "NOTE_FACT",
    "NOTE_FINDING",
    "NOTE_REMARK",
    "NOTE_TYPES",
    "NOTE_TYPES_BLOCKING",
    "NOTE_TYPES_BY_AGENT",
    "NOTE_TYPES_OPENABLE",
    "PRIORITY_BURNING",
    "PRIORITY_FROZEN",
    "PRIORITY_HIGH",
    "PRIORITY_LOW",
    "PRIORITY_NORMAL",
    "RESOLUTION_MAX",
    "SORT_DEFAULT",
    "SORT_STEP",
    "STAGE_CODE_PREFIX",
    "STAGE_STATUS_DEFAULT",
    "STATUS_BACKLOG",
    "STATUS_CANCELED",
    "STATUS_DONE",
    "STATUS_IN_PROGRESS",
    "STATUS_IN_REVIEW",
    "STATUS_IN_TEST",
    "STATUS_PLANNED",
    "TASK_CODE_PREFIX",
    "TASK_CREATED_BY_DEFAULT",
    "TASK_PRIORITIES",
    "TASK_PRIORITY_DEFAULT",
    "TASK_PRIORITY_WEIGHTS",
    "TASK_STATUSES",
    "TASK_STATUSES_TERMINAL",
    "TASK_STATUS_DEFAULT",
    "TASK_TYPES",
    "TASK_TYPES_WITH_PLAN",
    "TASK_TYPES_WITH_STAGES",
    "TASK_TYPE_DEFAULT",
    "TITLE_MAX",
    "TYPE_EXTENDED",
    "TYPE_SIMPLE",
    "TYPE_STANDARD",
    "sql_in",
]
