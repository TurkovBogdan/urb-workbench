// Справочники задачи на стороне интерфейса: порядок значений и их цвет.
//
// ВАЖНО: канонический источник самих значений — `src/modules/tasks/constants.py` (TASK_STATUSES,
// TASK_PRIORITIES, TASK_TYPES). Здесь их зеркало: бэк отдаёт голый код (`in_progress`), а
// интерфейсу нужны три вещи, которых в ответе нет и не будет, — в каком порядке показывать,
// каким цветом и какими словами. Слова живут в i18n (`tasks.task.status.*` и соседи), порядок и
// цвет — тут.
//
// Разошлось зеркало с константами — в выпадающем списке не хватит значения, а на карточке
// появится серый шильдик с кодом вместо подписи. Поэтому новое значение статуса или приоритета
// добавляется В ДВУХ местах: в кортеж `constants.py` и в массив ниже.

import {
  IconAntennaBars2,
  IconAntennaBars3,
  IconAntennaBars4,
  IconCircle,
  IconCircleCheck,
  IconCircleDashed,
  IconCircleX,
  IconEye,
  IconFlame,
  IconProgress,
  IconSnowflake,
  IconTestPipe,
} from '@tabler/icons-vue'

import type { TablerIcon } from '@/shared/nav'

type BadgeColor = 'accent' | 'success' | 'error' | 'warn' | 'muted'

// ── Длина текстовых полей ─────────────────────────────────────────────────────
// Потолки повторяют колонки БД (`constants.py`: TITLE_MAX / DESCRIPTION_MAX). Бэк длинное не
// примет (422), но узнать об этом после отправки — значит потерять набранное: поле само не даёт
// перебрать.
export const TASK_TITLE_MAX = 128
export const TASK_DESCRIPTION_MAX = 512
export const TASK_CONTEXT_MAX = 4048
export const TASK_CONSTRAINTS_MAX = 1024
export const TASK_CRITERIA_MAX = 1024
// Одна колонка на два поля: `BODY_MAX` в бэке держит и план задачи, и тело этапа. Имя здесь
// общее, чтобы на месте применения не казалось, будто у этапа потолок свой.
export const BODY_MAX = 8192
export const STAGE_EVIDENCE_MAX = 1024
export const NOTE_BODY_MAX = 2048
export const NOTE_RESOLUTION_MAX = 1024

// ── Порядок ───────────────────────────────────────────────────────────────────
// Шаг, с которым бэк перенумеровывает ряд соседей (`constants.py::SORT_STEP`). Стору он нужен,
// чтобы перестановка, применённая на экране до ответа, дала те же числа, что потом придут с бэка:
// тогда перечитка ничего не перерисовывает.
export const SORT_STEP = 5

// ── Статус ────────────────────────────────────────────────────────────────────
// Порядок — ход работы слева направо: из очереди в план, из плана в работу, дальше проверки и
// два исхода. Именно в этом порядке статус выбирают в форме, и алфавит тут был бы бессмыслицей.
export const TASK_STATUSES = [
  'backlog',
  'planned',
  'in_progress',
  'in_test',
  'in_review',
  'done',
  'canceled',
] as const

export type TaskStatus = (typeof TASK_STATUSES)[number]

// Цвет отвечает на вопрос «требует ли эта строка внимания»: работа идёт — акцент, ожидание
// чужого действия — предупреждающий, закрытое успехом — зелёный, отменённое — приглушённое
// (это не ошибка, а снятая работа).
export const TASK_STATUS_COLOR: Record<TaskStatus, BadgeColor> = {
  backlog: 'muted',
  planned: 'muted',
  in_progress: 'accent',
  in_test: 'warn',
  in_review: 'warn',
  done: 'success',
  canceled: 'muted',
}

// Глиф статуса: в плотной строке списка статус стоит слева значком, а не словом в шильдике —
// слово читается наравне с заголовком и спорит с ним за внимание, а очертание узнаётся боковым
// зрением и позволяет пробегать столбец значков сверху вниз. Название остаётся подсказкой.
// Ряд построен на одной форме — круг, — и состояние читается тем, что внутри него: пунктир
// (очереди ещё не касались), контур (взято в план), заполнение (идёт), галочка и крест (исходы).
// Две проверки выпадают из круга намеренно: тестирование и ревью — не фаза самой задачи, а
// ожидание чужого действия, и глиф у них предметный.
export const TASK_STATUS_ICON: Record<TaskStatus, TablerIcon> = {
  backlog: IconCircleDashed,
  planned: IconCircle,
  in_progress: IconProgress,
  in_test: IconTestPipe,
  in_review: IconEye,
  done: IconCircleCheck,
  canceled: IconCircleX,
}

// Работа по этим статусам окончена (зеркало TASK_STATUSES_TERMINAL): список приглушает такие
// карточки — они уже не про «что делать».
export const TASK_STATUSES_TERMINAL: readonly TaskStatus[] = ['done', 'canceled']

// ── Приоритет ─────────────────────────────────────────────────────────────────
// Порядок — по важности сверху вниз (зеркало TASK_PRIORITY_WEIGHTS: меньший вес важнее).
export const TASK_PRIORITIES = ['burning', 'high', 'normal', 'low', 'frozen'] as const

export type TaskPriority = (typeof TASK_PRIORITIES)[number]

export const TASK_PRIORITY_COLOR: Record<TaskPriority, BadgeColor> = {
  burning: 'error',
  high: 'warn',
  normal: 'muted',
  low: 'muted',
  frozen: 'muted',
}

// Глиф приоритета: три средних значения — шкала (уровень сигнала), и одинаковая форма с разной
// высотой столбиков читается как «больше-меньше» без чтения слов. Края шкалы — предметные:
// горящее и замороженное это не соседние деления, а другой разговор о задаче.
export const TASK_PRIORITY_ICON: Record<TaskPriority, TablerIcon> = {
  burning: IconFlame,
  high: IconAntennaBars4,
  normal: IconAntennaBars3,
  low: IconAntennaBars2,
  frozen: IconSnowflake,
}

// Обычный приоритет на карточке не показывается: он у большинства задач, и шильдик «обычный»
// на каждой строке говорил бы ровно ничего, зато занимал бы место рядом с теми, что важны.
export const TASK_PRIORITY_DEFAULT: TaskPriority = 'normal'

// ── Тип ───────────────────────────────────────────────────────────────────────
// Глубина ведения, а не адресат: простая — карточка без плана, стандартная — с постановкой,
// планом, этапами и журналом, расширенная — то же плюс плотный надзор (шлюзы, которые появятся
// на стороне MCP). Порядок — от лёгкого к тяжёлому.
export const TASK_TYPES = ['simple', 'standard', 'extended'] as const

export type TaskType = (typeof TASK_TYPES)[number]

// Простая задача — умолчание, и в списке её тип не показывается: пометка на каждой второй
// строке перестаёт что-либо значить. Видно ровно то, что отличает задачу от остальных.
export const TASK_TYPE_DEFAULT: TaskType = 'simple'

/**
 * Что показывает интерфейс у задачи этого типа.
 *
 * Тип НИЧЕГО НЕ СТИРАЕТ: переключение прячет лишние поля, а написанное остаётся в базе и
 * возвращается, если тип вернуть назад. Поэтому это карта видимости, а не набор разрешений.
 */
export interface TypeLayout {
  /** Границы и требования к сдаче — постановка, которой у простой задачи нет. */
  brief: boolean
  /** План агента прозой и журнал работы. */
  plan: boolean
  /** Полотно этапов. Только у расширенной — этим она от стандартной и отличается. */
  stages: boolean
}

// Граница между `standard` и `extended` проходит по этапам. План прозой отвечает на «как я это
// сделаю», этапы — на «где я сейчас и чем доказано пройденное»; второй вопрос осмыслен только у
// работы длиннее одного захода. Зеркало `constants.py::TASK_TYPES_WITH_PLAN/WITH_STAGES`.
const TYPE_LAYOUT: Record<TaskType, TypeLayout> = {
  simple: { brief: false, plan: false, stages: false },
  standard: { brief: true, plan: true, stages: false },
  extended: { brief: true, plan: true, stages: true },
}

/** Карта видимости по типу; незнакомое значение показывает всё — прятать по догадке нельзя. */
export function typeLayout(value: string): TypeLayout {
  return TYPE_LAYOUT[value as TaskType] ?? { brief: true, plan: true, stages: true }
}

// ── Виды записей журнала ──────────────────────────────────────────────────────
// Зеркало `constants.py::NOTE_TYPES`, порядок тот же — от частого к редкому.
export const NOTE_TYPES = ['decision', 'remark', 'finding', 'fact'] as const

export type NoteType = (typeof NOTE_TYPES)[number]

// Цвет отвечает на вопрос «чьё это и чего ждёт»: решение — наша работа (акцент), замечание
// постановщика — требует ответа (предупреждение), находка — чужой долг (нейтральное),
// факт — просто память, он ничего не ждёт.
export const NOTE_TYPE_COLOR: Record<NoteType, BadgeColor> = {
  decision: 'accent',
  remark: 'warn',
  finding: 'muted',
  fact: 'muted',
}

export function noteColor(value: string): BadgeColor {
  return NOTE_TYPE_COLOR[value as NoteType] ?? 'muted'
}

/** Значение из ответа бэка → член справочника; чужое значение возвращает `undefined`. */
export function asStatus(value: string): TaskStatus | undefined {
  return (TASK_STATUSES as readonly string[]).includes(value)
    ? (value as TaskStatus)
    : undefined
}

export function asPriority(value: string): TaskPriority | undefined {
  return (TASK_PRIORITIES as readonly string[]).includes(value)
    ? (value as TaskPriority)
    : undefined
}

/** Цвет шильдика статуса; незнакомое значение (бэк ушёл вперёд) рисуется нейтрально. */
export function statusColor(value: string): BadgeColor {
  const status = asStatus(value)
  return status ? TASK_STATUS_COLOR[status] : 'muted'
}

export function priorityColor(value: string): BadgeColor {
  const priority = asPriority(value)
  return priority ? TASK_PRIORITY_COLOR[priority] : 'muted'
}

/** Глиф статуса; незнакомое значение рисуется пустым кругом — «состояние есть, но не наше». */
export function statusIcon(value: string): TablerIcon {
  const status = asStatus(value)
  return status ? TASK_STATUS_ICON[status] : IconCircle
}

/** Глиф приоритета; незнакомое значение — середина шкалы, как и его цвет. */
export function priorityIcon(value: string): TablerIcon {
  const priority = asPriority(value)
  return priority ? TASK_PRIORITY_ICON[priority] : IconAntennaBars3
}

/** Работа по задаче окончена — карточка уходит в приглушённый тон. */
export function isTerminal(value: string): boolean {
  const status = asStatus(value)
  return status !== undefined && TASK_STATUSES_TERMINAL.includes(status)
}
