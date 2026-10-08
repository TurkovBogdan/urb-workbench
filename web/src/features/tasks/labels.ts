// Task vocabularies on the UI side: the order of values and their color.
//
// IMPORTANT: the canonical source of the values themselves is `src/modules/tasks/constants.py`
// (TASK_STATUSES, TASK_PRIORITIES, TASK_TYPES). This is their mirror: the backend returns a bare
// code (`in_progress`), while the UI needs three things the response does not and will not carry —
// in what order to show them, in what color and with what words. The words live in i18n
// (`tasks.task.status.*` and neighbours), order and color live here.
//
// If the mirror drifts from the constants, the dropdown will be missing a value and the card will
// show a grey badge with the code instead of a label. So a new status or priority value is added
// in TWO places: the tuple in `constants.py` and the array below.

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

// ── Text field lengths ────────────────────────────────────────────────────────
// The caps mirror the DB columns (`constants.py`: TITLE_MAX / DESCRIPTION_MAX). The backend will
// reject anything longer (422), but learning that after submit means losing what was typed: the
// field itself prevents overtyping.
export const TASK_TITLE_MAX = 128
export const TASK_DESCRIPTION_MAX = 512
// `GROUP_DESCRIPTION_MAX`: a group's description is one line under its name, not a goal.
export const GROUP_DESCRIPTION_MAX = 128
export const TASK_CONTEXT_MAX = 4048
export const TASK_CONSTRAINTS_MAX = 2048
export const TASK_CRITERIA_MAX = 2048
// The agent's work on a task, in the order the work goes: plan, progress, result.
export const TASK_PLAN_MAX = 8192
export const TASK_PROGRESS_MAX = 16384
export const TASK_RESULT_MAX = 2048
// The stage body — `BODY_MAX` on the backend, the module's name for an entity's only text.
export const BODY_MAX = 8192
export const STAGE_EVIDENCE_MAX = 1024
export const NOTE_BODY_MAX = 2048
export const NOTE_RESOLUTION_MAX = 1024

// ── Order ─────────────────────────────────────────────────────────────────────
// The step the backend renumbers a sibling row with (`constants.py::SORT_STEP`). The store needs
// it so that a reorder applied on screen before the response yields the same numbers the backend
// later returns: then the re-read redraws nothing.
export const SORT_STEP = 5

// ── Status ────────────────────────────────────────────────────────────────────
// The order is the flow of work left to right: backlog to plan, plan to work, then the checks and
// the two outcomes. This is the order a status is picked in the form, and alphabetical order would
// make no sense here.
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

// Color answers "does this row need attention": work in progress — accent, waiting on someone
// else's action — warning, closed successfully — green, canceled — muted (not an error, just work
// taken off the table).
export const TASK_STATUS_COLOR: Record<TaskStatus, BadgeColor> = {
  backlog: 'muted',
  planned: 'muted',
  in_progress: 'accent',
  in_test: 'warn',
  in_review: 'warn',
  done: 'success',
  canceled: 'muted',
}

// Status glyph: in a dense list row the status sits on the left as an icon, not as a word in a
// badge — a word reads on a par with the title and competes with it for attention, while a shape
// is recognised in peripheral vision and lets you scan the icon column top to bottom. The name
// stays as a tooltip. The set is built on one shape — a circle — and the state reads from what is
// inside it: dashed (backlog not yet touched), outline (planned), fill (in progress), check and
// cross (outcomes). The two checks break out of the circle on purpose: testing and review are not
// a phase of the task itself but waiting on someone else's action, so their glyph is pictorial.
export const TASK_STATUS_ICON: Record<TaskStatus, TablerIcon> = {
  backlog: IconCircleDashed,
  planned: IconCircle,
  in_progress: IconProgress,
  in_test: IconTestPipe,
  in_review: IconEye,
  done: IconCircleCheck,
  canceled: IconCircleX,
}

// Work in these statuses is over (mirror of TASK_STATUSES_TERMINAL): the list mutes such cards —
// they are no longer about "what to do".
export const TASK_STATUSES_TERMINAL: readonly TaskStatus[] = ['done', 'canceled']

// ── Priority ──────────────────────────────────────────────────────────────────
// Ordered by importance, top down (mirror of TASK_PRIORITY_WEIGHTS: lower weight is more important).
export const TASK_PRIORITIES = ['burning', 'high', 'normal', 'low', 'frozen'] as const

export type TaskPriority = (typeof TASK_PRIORITIES)[number]

export const TASK_PRIORITY_COLOR: Record<TaskPriority, BadgeColor> = {
  burning: 'error',
  high: 'warn',
  normal: 'muted',
  low: 'muted',
  frozen: 'muted',
}

// Priority glyph: the three middle values are a scale (signal strength), and the same shape with
// bars of different height reads as "more-less" without reading words. The ends of the scale are
// pictorial: burning and frozen are not adjacent notches but a different conversation about the
// task.
export const TASK_PRIORITY_ICON: Record<TaskPriority, TablerIcon> = {
  burning: IconFlame,
  high: IconAntennaBars4,
  normal: IconAntennaBars3,
  low: IconAntennaBars2,
  frozen: IconSnowflake,
}

// Normal priority is not shown on the card: most tasks have it, and a "normal" badge on every row
// would say nothing at all while taking space next to the ones that matter.
export const TASK_PRIORITY_DEFAULT: TaskPriority = 'normal'

// ── Type ──────────────────────────────────────────────────────────────────────
// Depth of tracking, not the audience: simple — a card without a plan, standard — with a brief,
// plan, stages and journal, extended — the same plus close supervision (gates that will appear on
// the MCP side). Ordered light to heavy.
export const TASK_TYPES = ['simple', 'standard', 'extended'] as const

export type TaskType = (typeof TASK_TYPES)[number]

// Simple is the default, and its type is not shown in the list: a mark on every other row stops
// meaning anything. Only what sets a task apart from the rest is visible.
export const TASK_TYPE_DEFAULT: TaskType = 'simple'

/**
 * What the UI shows for a task of this type.
 *
 * Type ERASES NOTHING: switching hides the extra fields, but what was written stays in the
 * database and comes back if the type is switched back. So this is a visibility map, not a set of
 * permissions.
 */
export interface TypeLayout {
  /** Constraints and acceptance criteria — the part of the brief a simple task does not have. */
  brief: boolean
  /** The agent's plan in prose and the work journal. */
  plan: boolean
  /** The stage board. Extended only — that is exactly what sets it apart from standard. */
  stages: boolean
}

// The line between `standard` and `extended` is the stages. A prose plan answers "how will I do
// this", stages answer "where am I now and what proves the done part"; the second question only
// makes sense for work longer than one sitting. Mirror of
// `constants.py::TASK_TYPES_WITH_PLAN/WITH_STAGES`.
const TYPE_LAYOUT: Record<TaskType, TypeLayout> = {
  simple: { brief: false, plan: false, stages: false },
  standard: { brief: true, plan: true, stages: false },
  extended: { brief: true, plan: true, stages: true },
}

/** Visibility map by type; an unknown value shows everything — never hide on a guess. */
export function typeLayout(value: string): TypeLayout {
  return TYPE_LAYOUT[value as TaskType] ?? { brief: true, plan: true, stages: true }
}

// ── Journal entry kinds ───────────────────────────────────────────────────────
// Mirror of `constants.py::NOTE_TYPES`, same order — most frequent to rarest.
export const NOTE_TYPES = ['decision', 'remark', 'finding', 'fact'] as const

export type NoteType = (typeof NOTE_TYPES)[number]

// Color answers "whose is this and what is it waiting for": a decision is our work (accent), the
// task author's remark needs an answer (warning), a finding is someone else's debt (neutral),
// a fact is just memory and waits for nothing.
export const NOTE_TYPE_COLOR: Record<NoteType, BadgeColor> = {
  decision: 'accent',
  remark: 'warn',
  finding: 'muted',
  fact: 'muted',
}

export function noteColor(value: string): BadgeColor {
  return NOTE_TYPE_COLOR[value as NoteType] ?? 'muted'
}

/** A value from the backend response → a vocabulary member; a foreign value returns `undefined`. */
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

/** Status badge color; an unknown value (the backend moved ahead) is drawn neutral. */
export function statusColor(value: string): BadgeColor {
  const status = asStatus(value)
  return status ? TASK_STATUS_COLOR[status] : 'muted'
}

export function priorityColor(value: string): BadgeColor {
  const priority = asPriority(value)
  return priority ? TASK_PRIORITY_COLOR[priority] : 'muted'
}

/** Status glyph; an unknown value is drawn as an empty circle — "there is a state, not ours". */
export function statusIcon(value: string): TablerIcon {
  const status = asStatus(value)
  return status ? TASK_STATUS_ICON[status] : IconCircle
}

/** Priority glyph; an unknown value gets the middle of the scale, as does its color. */
export function priorityIcon(value: string): TablerIcon {
  const priority = asPriority(value)
  return priority ? TASK_PRIORITY_ICON[priority] : IconAntennaBars3
}

/** Work on the task is over — the card goes into a muted tone. */
export function isTerminal(value: string): boolean {
  const status = asStatus(value)
  return status !== undefined && TASK_STATUSES_TERMINAL.includes(status)
}
