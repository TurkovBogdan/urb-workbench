/**
 * Клиент API модуля tasks (бэк: /internal/workbench).
 *
 * Префикс `/workbench`, а не `/tasks`: корень `/internal/tasks` занят расписанием планировщика
 * (`core_monitoring` смонтирован без префикса и держит там `/tasks` и `/tasks/{module}/{code}`).
 * Пока наш модуль стоял на `/tasks`, запрос задачи — `/internal/tasks/tasks/{code}` — уходил в
 * его маршрут и возвращал `{"error": "task not registered"}`: деталка не работала вовсе.
 *
 * Четыре поверхности: группы (темы внутри пространства), задачи, этапы плана и журнал работы.
 * Само пространство живёт в своём модуле (`features/workspace/api.ts`) — отсюда в запросы едет
 * только его код. Списки групп и задач всегда спрашивают про КОНКРЕТНОЕ пространство: поперёк
 * пространств модуль не читает, и `workspace` у них обязателен.
 *
 * Коды приходят с префиксом (GROUP@…, TASK@…, STAGE@…, NOTE@…, WORKSPACE@…) и в таком же виде
 * уезжают обратно: бэк снимает префикс сам, а в сегмент адреса он кодируется через
 * `encodeURIComponent` — «@» в пути разрешён, но кодирование безопаснее для любых будущих форм.
 *
 * Даты — SQL-формат (dto.py::DatetimeUTCStr), форматирует shared/utils/date.
 */

import { internalApi, type RequestOptions } from '@/api/client/internal'

const BASE = '/workbench'

const seg = (code: string) => encodeURIComponent(code)

// ── Группы ────────────────────────────────────────────────────────────────────

/**
 * Группа — долгоживущая тема внутри пространства (биллинг, интерфейс, инфраструктура). Ими список
 * задач рисует заголовки секций, а заводят и правят их на своей странице — набор ручек такой же,
 * как у пространства, кроме одного: пространство группы задаётся при создании и правкой не
 * меняется, иначе перенос группы утащил бы за собой все её задачи.
 */
export interface GroupRow {
  code: string
  workspace_code: string
  title: string
  description: string
  /** Имя из реестра `shared/colors.ts`; пустое — цвет не выбран. */
  color: string
  /** Имя из реестра `shared/icons.ts`; пустое — иконка не выбрана. */
  icon: string
  /** Больший `sort` — выше в списке. */
  sort: number
  created_at: string
  updated_at: string
  deleted_at: string | null
}

/** Строка списка групп: карточка плюс сколько внутри живых задач. */
export interface GroupListRow extends GroupRow {
  task_count: number
}

export interface GroupBody {
  title: string
  description: string
  color: string
  icon: string
  /** Позиция среди соседей: больший `sort` — выше. */
  sort: number
}

export interface ListGroupsParams {
  /** Код пространства — обязателен: группа вне пространства не существует. */
  workspace: string
  include_deleted?: boolean
}

export async function listGroups(
  params: ListGroupsParams,
  opts?: RequestOptions,
): Promise<GroupListRow[]> {
  return internalApi.get<GroupListRow[]>(`${BASE}/groups`, { ...opts, query: { ...params } })
}

export async function getGroup(code: string, opts?: RequestOptions): Promise<GroupRow> {
  return internalApi.get<GroupRow>(`${BASE}/groups/${seg(code)}`, opts)
}

/** Пространство едет параметром запроса, а не в теле: правка его не принимает вовсе. */
export async function createGroup(
  workspace: string,
  body: GroupBody,
  opts?: RequestOptions,
): Promise<GroupRow> {
  return internalApi.post<GroupRow>(`${BASE}/groups`, body, { ...opts, query: { workspace } })
}

export async function updateGroup(
  code: string,
  body: GroupBody,
  opts?: RequestOptions,
): Promise<GroupRow> {
  return internalApi.put<GroupRow>(`${BASE}/groups/${seg(code)}`, body, opts)
}

/**
 * Перетаскивание карточки группы: соседка, относительно которой она встала.
 *
 * Ровно одна из двух точек отсчёта — двух сразу бэк не принимает, и ни одной тоже: «переставь
 * куда-нибудь» это не позиция. Номера здесь нет намеренно, `sort` человеку на экране не виден.
 */
export async function reorderGroup(
  code: string,
  body: { after_code?: string | null; before_code?: string | null },
  opts?: RequestOptions,
): Promise<GroupRow> {
  return internalApi.post<GroupRow>(`${BASE}/groups/${seg(code)}/reorder`, body, opts)
}

/** Мягкое удаление: задачи остаются в группе, и `restoreGroup` возвращает раскладку как была. */
export async function deleteGroup(code: string, opts?: RequestOptions): Promise<void> {
  await internalApi.del<void>(`${BASE}/groups/${seg(code)}`, undefined, opts)
}

export async function restoreGroup(code: string, opts?: RequestOptions): Promise<GroupRow> {
  return internalApi.post<GroupRow>(`${BASE}/groups/${seg(code)}/restore`, undefined, opts)
}

/** Физическое удаление группы: задачи переживают её и уходят в секцию «Без группы». */
export async function purgeGroup(code: string, opts?: RequestOptions): Promise<void> {
  await internalApi.del<void>(`${BASE}/groups/${seg(code)}/purge`, undefined, opts)
}

// ── Задачи ────────────────────────────────────────────────────────────────────

/** Собственные поля задачи — всё, что лежит в её строке, кроме постановки и плана. */
export interface TaskRow {
  code: string
  workspace_code: string
  /** Группа (`GROUP@…`) или `null` — задача вне групп, ей место в секции «Без группы». */
  group_code: string | null
  /** `simple` | `standard` | `extended` — глубина ведения, см. `labels.ts`. */
  type: string
  status: string
  priority: string
  title: string
  /** Цель: что станет правдой, когда работа сделана. */
  description: string
  /** `human` | `agent` — кто завёл строку. */
  created_by: string
  /** Крайний срок — единственная назначаемая задаче дата. */
  deadline_at: string | null
  started_at: string | null
  completed_at: string | null
  canceled_at: string | null
  created_at: string
  updated_at: string
  /** Не null — задача в корзине: правка ей недоступна, доступны восстановление и снос. */
  deleted_at: string | null
}

/** Строка списка: карточка задачи плюс её место в дереве. */
export interface TaskListRow extends TaskRow {
  /** Родитель (`TASK@…`) или `null` — корень пространства. */
  parent_code: string | null
  /** Позиция среди соседей: больший `sort` — выше. */
  sort: number
  /** Под задачей есть ещё задачи — список рисует этим пометку, а не раскрывает ветку. */
  has_children: boolean
}

/** Этап плана: шаг работы со своим состоянием и доказательством выполнения. */
export interface StageRow {
  code: string
  task_code: string
  /** Номер растёт вниз: первый этап — единица. */
  number: number
  status: string
  title: string
  description: string
  body: string
  /** Указатель на доказательство: команда и её итог, путь, диф. Без него этап не закрыть. */
  evidence: string
  started_at: string | null
  finished_at: string | null
  created_at: string
  updated_at: string
}

export interface StageBody {
  title: string
  description: string
  body: string
  evidence: string
  /** Не передан — этап встаёт следующим по счёту. */
  number?: number | null
}

/**
 * Запись журнала: предмет (`title` + `body`) и разрешение. Пустое `resolution` — запись открыта.
 *
 * `type`: `decision` (выбор по ходу), `remark` (замечание постановщика), `finding` (находка вне
 * задачи), `fact` (то, что нужно помнить). Факт закрыт в момент записи.
 */
export interface NoteRow {
  code: string
  task_code: string
  stage_code: string | null
  type: string
  title: string
  body: string
  resolution: string
  created_at: string
}

export interface NoteBody {
  type: string
  title: string
  body: string
  resolution?: string
  stage_code?: string | null
}

/**
 * Задача целиком. Группа и родитель приезжают строками, а не одними кодами: страница показывает
 * их названиями, и добывать названия двумя дополнительными запросами на каждое открытие незачем.
 * Этапы и журнал едут здесь же — деталь задачи и есть экран работы.
 */
export interface TaskDetail extends TaskListRow {
  /** Детали и стартовые требования; markdown. */
  context: string
  /** Что можно и чего нельзя; markdown-список. */
  constraints: string
  /** Требования к формату сдачи и к этапам; markdown-список. */
  criteria: string
  /** План агента; markdown. */
  body: string
  group: GroupRow | null
  parent: TaskListRow | null
  children: TaskListRow[]
  stages: StageRow[]
  notes: NoteRow[]
}

export interface TaskCreateBody {
  workspace: string
  title: string
  description?: string
  context?: string
  constraints?: string
  criteria?: string
  body?: string
  type?: string
  status?: string
  priority?: string
  group_code?: string | null
  parent_code?: string | null
  deadline_at?: string | null
}

/**
 * Правка — полная замена карточки: не переданное поле бэк стирает. Поэтому форма всегда шлёт
 * все поля, а не только изменённые, иначе снять группу или срок было бы нечем.
 *
 * Статуса здесь нет намеренно: его меняет `setTaskStatus` — только этот путь ставит отметки
 * времени начала, завершения и отмены.
 */
export interface TaskUpdateBody {
  title: string
  description: string
  context: string
  constraints: string
  criteria: string
  body: string
  type: string
  priority: string
  group_code: string | null
  deadline_at: string | null
}

export interface ListTasksParams {
  workspace: string
  include_deleted?: boolean
  status?: string
  /** Код группы; пустая строка — только задачи вне групп (секция «Без группы»). */
  group?: string
}

export async function listTasks(
  params: ListTasksParams,
  opts?: RequestOptions,
): Promise<TaskListRow[]> {
  return internalApi.get<TaskListRow[]>(`${BASE}/tasks`, { ...opts, query: { ...params } })
}

/**
 * Области глубокого поиска: что, кроме заголовка и цели, входит в стог.
 *
 * Ни одна не включена по умолчанию — ни здесь, ни на бэке: поиск, тихо залезающий в тела по
 * восемь килобайт, возвращает совпадения, по которым не понять, та ли это задача.
 */
export interface SearchTasksParams {
  workspace: string
  query: string
  /** Постановка: контекст, границы, критерии. */
  in_brief?: boolean
  /** План задачи и тела её этапов. */
  in_plan?: boolean
  /** Записи журнала. */
  in_journal?: boolean
}

/**
 * Коды задач, у которых запрос нашёлся В ТЕЛАХ — вторая половина поиска по списку.
 *
 * Заголовок и цель есть в каждой строке, и по ним ищет сам список — мгновенно и без круга по
 * сети. Сюда ходят только за тем, чего в строке нет, поэтому и ответ — одни коды: карточки у
 * спрашивающего уже есть, и он пересекает их со своим списком.
 */
export async function searchTasks(
  params: SearchTasksParams,
  opts?: RequestOptions,
): Promise<string[]> {
  return internalApi.get<string[]>(`${BASE}/tasks/search`, { ...opts, query: { ...params } })
}

export async function getTask(code: string, opts?: RequestOptions): Promise<TaskDetail> {
  return internalApi.get<TaskDetail>(`${BASE}/tasks/${seg(code)}`, opts)
}

export async function createTask(
  body: TaskCreateBody,
  opts?: RequestOptions,
): Promise<TaskDetail> {
  return internalApi.post<TaskDetail>(`${BASE}/tasks`, body, opts)
}

export async function updateTask(
  code: string,
  body: TaskUpdateBody,
  opts?: RequestOptions,
): Promise<TaskDetail> {
  return internalApi.put<TaskDetail>(`${BASE}/tasks/${seg(code)}`, body, opts)
}

/**
 * Частичная правка: уходят только названные поля, остальные на бэке не трогаются. Так страница
 * задачи, сохраняя одно поле, не откатывает то, что тем временем записал агент. `null` у группы
 * и срока — снять их.
 */
export async function patchTask(
  code: string,
  body: Partial<TaskUpdateBody>,
  opts?: RequestOptions,
): Promise<TaskDetail> {
  return internalApi.patch<TaskDetail>(`${BASE}/tasks/${seg(code)}`, body, opts)
}

/** Смена статуса — своя ручка: вместе со статусом бэк ставит отметку фазы. */
export async function setTaskStatus(
  code: string,
  status: string,
  opts?: RequestOptions,
): Promise<TaskDetail> {
  return internalApi.post<TaskDetail>(`${BASE}/tasks/${seg(code)}/status`, { status }, opts)
}

/** Перенос ветки: новый родитель (`null` — корень) и позиция среди соседей. */
export async function moveTask(
  code: string,
  body: { parent_code: string | null; sort?: number | null },
  opts?: RequestOptions,
): Promise<TaskDetail> {
  return internalApi.post<TaskDetail>(`${BASE}/tasks/${seg(code)}/move`, body, opts)
}

/**
 * Перетаскивание строки списка: после какой задачи она легла и, если её тянули в чужую карточку,
 * в какой она теперь группе.
 *
 * Позиция названа СОСЕДОМ, а не номером: у списка на экране свои фильтры и страницы, и номер
 * строки в нём не совпадает с номером среди соседей в базе. `after_code: null` — в начало ряда.
 *
 * Ключ `group_code` отсутствует — группу не трогаем, `null` — снимаем: перестановка внутри своей
 * карточки про группы знать не должна, а переезд в «Без группы» обязан уметь её снять.
 *
 * `parent_code` устроен так же: ключа нет — родителя не трогаем, `null` — открепить. Так
 * выражается второй жест списка: подзадачу вытащили из ветки, и она стала обычной задачей.
 */
export async function reorderTask(
  code: string,
  body: {
    after_code: string | null
    group_code?: string | null
    parent_code?: string | null
  },
  opts?: RequestOptions,
): Promise<TaskDetail> {
  return internalApi.post<TaskDetail>(`${BASE}/tasks/${seg(code)}/reorder`, body, opts)
}

/** Мягкое удаление — вместе со всей веткой под задачей; вернуть можно `restoreTask`. */
export async function deleteTask(code: string, opts?: RequestOptions): Promise<void> {
  await internalApi.del<void>(`${BASE}/tasks/${seg(code)}`, undefined, opts)
}

export async function restoreTask(code: string, opts?: RequestOptions): Promise<TaskDetail> {
  return internalApi.post<TaskDetail>(`${BASE}/tasks/${seg(code)}/restore`, undefined, opts)
}

/** Физическое удаление задачи вместе с веткой: вернуть будет нечего. */
export async function purgeTask(code: string, opts?: RequestOptions): Promise<void> {
  await internalApi.del<void>(`${BASE}/tasks/${seg(code)}/purge`, undefined, opts)
}

// ── Этапы плана ───────────────────────────────────────────────────────────────

export async function listStages(
  taskCode: string,
  opts?: RequestOptions,
): Promise<StageRow[]> {
  return internalApi.get<StageRow[]>(`${BASE}/tasks/${seg(taskCode)}/stages`, opts)
}

export async function createStage(
  taskCode: string,
  body: Omit<StageBody, 'evidence'> & { evidence?: string },
  opts?: RequestOptions,
): Promise<StageRow> {
  return internalApi.post<StageRow>(`${BASE}/tasks/${seg(taskCode)}/stages`, body, opts)
}

export async function updateStage(
  code: string,
  body: StageBody,
  opts?: RequestOptions,
): Promise<StageRow> {
  return internalApi.put<StageRow>(`${BASE}/stages/${seg(code)}`, body, opts)
}

/** Закрытие этапа: `done` с пустым `evidence` бэк отклоняет — это и есть шлюз. */
export async function setStageStatus(
  code: string,
  status: string,
  opts?: RequestOptions,
): Promise<StageRow> {
  return internalApi.post<StageRow>(`${BASE}/stages/${seg(code)}/status`, { status }, opts)
}

export async function deleteStage(code: string, opts?: RequestOptions): Promise<void> {
  await internalApi.del<void>(`${BASE}/stages/${seg(code)}`, undefined, opts)
}

// ── Журнал ────────────────────────────────────────────────────────────────────

export interface ListNotesParams {
  type?: string
  open_only?: boolean
}

export async function listNotes(
  taskCode: string,
  params?: ListNotesParams,
  opts?: RequestOptions,
): Promise<NoteRow[]> {
  return internalApi.get<NoteRow[]>(`${BASE}/tasks/${seg(taskCode)}/notes`, {
    ...opts,
    query: { ...params },
  })
}

export async function createNote(
  taskCode: string,
  body: NoteBody,
  opts?: RequestOptions,
): Promise<NoteRow> {
  return internalApi.post<NoteRow>(`${BASE}/tasks/${seg(taskCode)}/notes`, body, opts)
}

/** Закрыть запись. Повторное закрытие бэк отклоняет: журнал дописываемый. */
export async function resolveNote(
  code: string,
  resolution: string,
  opts?: RequestOptions,
): Promise<NoteRow> {
  return internalApi.post<NoteRow>(`${BASE}/notes/${seg(code)}/resolve`, { resolution }, opts)
}

export async function deleteNote(code: string, opts?: RequestOptions): Promise<void> {
  await internalApi.del<void>(`${BASE}/notes/${seg(code)}`, undefined, opts)
}
