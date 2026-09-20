"""DTO модуля ``tasks`` — контракты обеих поверхностей: web-вьюера и агента.

**Префикс ``Agent`` = поверхность агента.** Класс с этим префиксом возвращается тулами MCP
(``mcp/``) и больше никем, всё остальное — контракты web-вьюера. Граница сплошная: общих
контрактов у поверхностей нет даже там, где наборы полей совпадают. Общий контракт разъезжается
в одну сторону — поле, добавленное ради колонки в таблице, молча начинает стоить агенту
контекста в каждой сессии.

Докстринга у агентского класса нет намеренно: pydantic кладёт его в JSON-схему тула описанием, и
агент оплачивает его при каждом подключении. Поэтому пояснения агентских контрактов живут в
комментариях НАД классом.

Код в выдаче несёт презентационный префикс (``WORKSPACE@…``) — за это отвечает ``prefixed``
из ``tasks.codes``: сериализатор надевает тип-слово только в JSON, внутренний ``model_dump()``
остаётся голым. На вход код принимается в обеих формах — снимает префикс ``bare_code`` на
границе ручки, а не здесь: DTO описывает ответ, разбор адреса — работа маршрута.

Даты отдаются ядровым ``DatetimeUTCStr`` (SQL-формат без ``T``) — ровно его ждёт фронт-парсер
``web/src/shared/utils/date.ts`` (Luxon ``fromSQL``). ISO с ``T`` он не разбирает, и дата на
карточке молча превратилась бы в «неверную».

Карточки пространства здесь нет: она живёт в модуле ``workspace`` вместе с самой сущностью.
Отсюда наружу едет только ССЫЛКА на него — ``workspace_code`` с префиксом, собранным из чужой
константы: тип-слово принадлежит владельцу сущности, а не тому, кто на неё ссылается.

У задачи место в дереве едет **в той же строке**, что и её поля (``parent_code`` / ``sort``),
хотя в базе они лежат в отдельной таблице (``tasks_link``). Разделение
там нужно записи (перенос ветки не переписывает карточку), а читателю — нет: списку всё равно
нужны обе половины сразу, и второй запрос за рёбрами он бы всё равно сделал.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from src.core.utils.date import DatetimeUTCStr
from src.modules.tasks.codes import prefixed
from src.modules.tasks.constants import (
    GROUP_CODE_PREFIX,
    NOTE_CODE_PREFIX,
    SORT_DEFAULT,
    STAGE_CODE_PREFIX,
    TASK_CODE_PREFIX,
    TASK_PRIORITY_DEFAULT,
    TASK_STATUS_DEFAULT,
    TASK_TYPE_DEFAULT,
)
from src.modules.workspace.constants import WORKSPACE_CODE_PREFIX
from src.modules.workspace.dto import AgentScope

# Презентационный тип кода: голый хеш внутрь, ``WORKSPACE@<hash>`` наружу. Префикс пространства
# взят у его модуля: переименуй он своё тип-слово — ссылка поедет следом сама.
WorkspaceCode = prefixed(WORKSPACE_CODE_PREFIX)
GroupCode = prefixed(GROUP_CODE_PREFIX)
TaskCode = prefixed(TASK_CODE_PREFIX)
StageCode = prefixed(STAGE_CODE_PREFIX)
NoteCode = prefixed(NOTE_CODE_PREFIX)


class GroupRow(BaseModel):
    """Группа задач — заголовок секции в списке задач и карточка в своём разделе."""

    model_config = ConfigDict(from_attributes=True)

    code: GroupCode
    workspace_code: WorkspaceCode
    title: str
    description: str = ""
    color: str = ""
    icon: str = ""
    sort: int = SORT_DEFAULT
    created_at: DatetimeUTCStr
    updated_at: DatetimeUTCStr
    deleted_at: DatetimeUTCStr | None = None


class GroupListRow(GroupRow):
    """Строка списка групп: карточка плюс счётчик живых задач внутри.

    Счётчик тут по той же причине, что и у пространства: группа существует ради того, чтобы в ней
    что-то лежало, и «удалить» без числа было бы предложением подтвердить неизвестное.
    """

    task_count: int = 0


class TaskRow(BaseModel):
    """Собственные поля задачи — всё, что лежит в ``tasks_task``, кроме тела.

    Тела здесь нет намеренно: в списке оно не показывается ни одной строкой, а весит больше
    всей остальной карточки вместе взятой. Его отдаёт только деталь (``TaskDetail``).

    Отметки фаз (``started_at`` / ``completed_at`` / ``canceled_at``) едут и в списке: это
    единственный способ отличить «сделано вчера» от «сделано в марте», не открывая задачу.
    """

    model_config = ConfigDict(from_attributes=True)

    code: TaskCode
    workspace_code: WorkspaceCode
    group_code: GroupCode | None = None
    type: str = TASK_TYPE_DEFAULT
    status: str = TASK_STATUS_DEFAULT
    priority: str = TASK_PRIORITY_DEFAULT
    title: str
    description: str = ""
    created_by: str
    deadline_at: DatetimeUTCStr | None = None
    started_at: DatetimeUTCStr | None = None
    completed_at: DatetimeUTCStr | None = None
    canceled_at: DatetimeUTCStr | None = None
    created_at: DatetimeUTCStr
    updated_at: DatetimeUTCStr
    deleted_at: DatetimeUTCStr | None = None


class TaskListRow(TaskRow):
    """Строка списка: карточка задачи плюс её место в дереве и признак ветки под ней.

    ``has_children`` — признак, а не счётчик: список рисует им пометку «внутри есть ещё», а
    точное число там негде показать, и считать его на каждую строку значило бы платить за то,
    чего не видно. Сам список плоский: дерево раскрывает деталь.
    """

    parent_code: TaskCode | None = None
    sort: int = SORT_DEFAULT
    has_children: bool = False


class StageRow(BaseModel):
    """Этап плана — строка полотна и карточка в детали задачи."""

    model_config = ConfigDict(from_attributes=True)

    code: StageCode
    task_code: TaskCode
    number: int
    status: str
    title: str
    description: str = ""
    body: str = ""
    evidence: str = ""
    started_at: DatetimeUTCStr | None = None
    finished_at: DatetimeUTCStr | None = None
    created_at: DatetimeUTCStr
    updated_at: DatetimeUTCStr


class NoteRow(BaseModel):
    """Запись журнала: предмет (``title`` + ``body``) и разрешение.

    Отдельного признака «открыта» нет: он выводится из пустого ``resolution``, и держать рядом
    вычислимый флаг значило бы завести второй источник правды о том же.
    """

    model_config = ConfigDict(from_attributes=True)

    code: NoteCode
    task_code: TaskCode
    stage_code: StageCode | None = None
    type: str
    title: str
    body: str = ""
    resolution: str = ""
    created_at: DatetimeUTCStr


class TaskDetail(TaskListRow):
    """Задача целиком: постановка, план, соседи по дереву, группа, этапы и журнал.

    Дети — такие же строки списка (с их собственными рёбрами и признаком ветки), поэтому
    карточка ребёнка на детали и карточка в списке — один и тот же объект: разойтись их
    разметке негде.

    Группа и родитель едут строками, а не одними кодами, хотя коды в ответе тоже есть. Причина
    прикладная: страница показывает их НАЗВАНИЯМИ («Биллинг», «Счета»), а из кода названия не
    добыть — клиенту пришлось бы делать два дополнительных запроса на каждое открытие задачи
    ради двух строк текста. Коды при этом остаются: по ним работает правка и перенос.

    Этапы и журнал едут здесь же: деталь задачи — это и есть экран работы, и второй запрос за
    планом клиент сделал бы всё равно. У простой задачи оба списка пустые — их просто некому
    заводить.
    """

    context: str = ""
    constraints: str = ""
    criteria: str = ""
    body: str = ""
    group: GroupRow | None = None
    parent: TaskListRow | None = None
    children: list[TaskListRow] = []
    stages: list[StageRow] = []
    notes: list[NoteRow] = []


# Группа глазами агента: куда класть задачу и что там уже лежит. Оформления (цвет, иконка) здесь
# нет — их рисует интерфейс, а агенту они сказали бы ровно ничего и стоили бы двух полей в каждой
# строке ответа; поверхности разведены, и общего контракта у них не будет даже там, где наборы
# полей совпадут. ``description`` наоборот обязателен по смыслу: в нём границы группы, и по ним
# агент решает, в какую класть новую задачу, — по одному названию он ошибается чаще.
class AgentGroupRow(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    code: GroupCode
    title: str
    description: str = ""
    task_count: int = 0


# Группы активного пространства — вместе с тем, какое пространство это было (``AgentScope``).
# Тот же тип отвечает и на правку раскладки: после заведения или перестановки группы агенту нужно
# не эхо присланного, а новое состояние списка — счётчики и порядок он своей правкой сдвинул и
# иначе пошёл бы за ними вторым вызовом.
class AgentGroupList(AgentScope):
    groups: list[AgentGroupRow] = []


# Раскладка после переноса пачки задач: те же группы плюс сколько строк легло. Коды задач назад
# не едут — их агент только что передал сам; счётчики обеих затронутых групп он не знает.
class AgentTasksRegrouped(AgentGroupList):
    moved: int = 0


# ── задача ────────────────────────────────────────────────────────────────────
# Строка сканирующего слоя: то, по чему выбирают, за чтó браться. Постановки и плана здесь нет —
# за ними идут в ``task_get``; тянуть их на весь список дороже, чем прочесть список дважды.
# ``description`` (цель) остаётся: без него строка отвечает только «как называется», а решение
# принимают по «что станет правдой».
class AgentTaskRow(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    code: TaskCode
    title: str
    description: str = ""
    status: str
    priority: str
    type: str
    group_code: GroupCode | None = None
    parent_code: TaskCode | None = None
    has_children: bool = False
    deadline_at: DatetimeUTCStr | None = None


# ``shown`` против ``total`` — потолок выдачи, показанный числом, а не умолчанием в схеме.
# Разрыв виден сразу, и описание говорит, что сузить; аргумент ``limit`` стоил бы поля в каждом
# вызове ради того, что решается одной строкой ответа.
class AgentTaskList(AgentScope):
    tasks: list[AgentTaskRow] = []
    shown: int = 0
    total: int = 0


# Этап плана: шаг с собственным состоянием и собственным доказательством.
class AgentStageRow(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    code: StageCode
    number: int
    status: str
    title: str
    description: str = ""
    body: str = ""
    evidence: str = ""


# Запись журнала. Признака «открыта» нет — он выводится из пустого ``resolution``, и держать
# рядом вычислимый флаг значило бы завести второй источник правды о том же.
class AgentNoteRow(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    code: NoteCode
    type: str
    title: str
    body: str = ""
    resolution: str = ""
    stage_code: StageCode | None = None
    created_at: DatetimeUTCStr


# Рабочий экран: постановка, план, этапы и то, что ещё не закрыто.
#
# Закрытых записей журнала здесь нет, только их число: они отвечают на вопрос «как дошли», а его
# задают отдельно и редко. У долгой задачи журнал длиннее постановки, и возить его в каждом
# чтении значит платить за то, что читают раз.
#
# Группа и родитель едут кодом И названием: страницу агент не открывает, а из кода названия не
# добыть — пришлось бы звать ещё два инструмента ради двух строк текста.
class AgentTaskDetail(AgentScope):
    code: TaskCode
    title: str
    description: str = ""
    context: str = ""
    constraints: str = ""
    criteria: str = ""
    body: str = ""
    status: str
    priority: str
    type: str
    created_by: str
    group_code: GroupCode | None = None
    group_title: str = ""
    parent_code: TaskCode | None = None
    parent_title: str = ""
    deadline_at: DatetimeUTCStr | None = None
    started_at: DatetimeUTCStr | None = None
    completed_at: DatetimeUTCStr | None = None
    canceled_at: DatetimeUTCStr | None = None
    children: list[AgentTaskRow] = []
    stages: list[AgentStageRow] = []
    open_notes: list[AgentNoteRow] = []
    closed_notes: int = 0
    unfinished_stages: int = 0


# Расписка о заведении: код и пространство, больше ничего. Эхо собственного ввода агент оплатил
# бы на каждой заведённой строке, а знает он его и так.
class AgentTaskCreated(AgentScope):
    code: TaskCode


class AgentStageCreated(AgentScope):
    code: StageCode
    number: int


class AgentNoteCreated(AgentScope):
    code: NoteCode


# Ответ на смену статуса несёт не только новый статус, но и то, что ещё висит на задаче: это
# единственный момент, когда агент про это думает. ``blocking_notes`` — те, что держат сдачу
# (решение и замечание); ``open_notes`` шире на находки, которые разбирает человек.
class AgentTaskStatus(AgentScope):
    code: TaskCode
    status: str
    open_notes: int = 0
    blocking_notes: int = 0
    unfinished_stages: int = 0


# Ответ правки этапа несёт статус ЗАДАЧИ рядом со статусом этапа: старт этапа задачу не двигает,
# и без этой строки расхождение видно только тому, кто за ним следит.
class AgentStageChanged(AgentScope):
    stage: AgentStageRow
    task_code: TaskCode
    task_status: str


class AgentNoteList(AgentScope):
    notes: list[AgentNoteRow] = []


# ── редактор тела ─────────────────────────────────────────────────────────────
# Правка тела отвечает тем, чего агент ещё не знает. Присланный им текст назад не едет ни в
# каком виде: он его только что написал, а платить за эхо пришлось бы на каждой правке.
#
# ``body_set`` — расписка: тело и есть присланный текст, шва там нет, и сообщить можно только
# новую длину (заодно видно, сколько осталось до потолка — а потолок отказывает, не усекает).
class AgentBodySet(BaseModel):
    code: str
    length: int


# Шов — окно тела по обе стороны правки с заглушкой на месте текста. Он показывает ровно то, что
# нельзя было предвидеть: во что вставка упёрлась слева и справа.
class AgentBodyAdded(BaseModel):
    code: str
    edit: str


# ``replaced`` совпадает с длиной ``edits``: швы идут в порядке документа, по одному на вхождение.
class AgentBodyReplaced(BaseModel):
    code: str
    replaced: int
    edits: list[str] = []


# У правки раздела непредсказуем не стык, а размах выреза: границу считает сервер по уровню
# заголовка. Поэтому ответ показывает вырезанное, его настоящую длину и заголовок, на котором
# вырез остановился. Раздел, который считали коротким, вернувшийся длинным, — это вырез, ушедший
# дальше, чем думали, и заметить это можно только здесь: вырезанное нигде не сохраняется.
class AgentBodySectionSet(BaseModel):
    code: str
    removed: str
    removed_length: int
    stopped_at: str | None = None


__all__ = [
    "AgentBodyAdded",
    "AgentBodyReplaced",
    "AgentBodySectionSet",
    "AgentBodySet",
    "AgentGroupList",
    "AgentGroupRow",
    "AgentNoteCreated",
    "AgentNoteList",
    "AgentNoteRow",
    "AgentStageChanged",
    "AgentStageCreated",
    "AgentStageRow",
    "AgentTaskCreated",
    "AgentTaskDetail",
    "AgentTaskList",
    "AgentTaskRow",
    "AgentTaskStatus",
    "AgentTasksRegrouped",
    "GroupCode",
    "GroupListRow",
    "GroupRow",
    "NoteCode",
    "NoteRow",
    "StageCode",
    "StageRow",
    "TaskCode",
    "TaskDetail",
    "TaskListRow",
    "TaskRow",
    "WorkspaceCode",
]
