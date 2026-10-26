// The shape of an import's plan as every transfer answers it (`core_transfer` on the backend): the
// archive's passport, the conflicts of codes with their options and dates, the notices. A feature
// adds its own root and counts on top.

export type TransferChoice = 'update' | 'replace'

/** One side of a conflict: when it changed, when it appeared, how large it is. */
export interface TransferSide {
  updated_at: string | null
  created_at: string | null
  size: number | null
}

export interface TransferConflict {
  /** The archive's entity with its prefix — unique within a plan. */
  id: string
  /** The feature's word for the kind: `task`, `subtask`, `note`, `codex`, `record`, `file`. */
  entity: string
  title: string
  /** What holds the code here: its kind, code, title, holder. */
  local: Record<string, string>
  options: TransferChoice[]
  /** Why «update» is not offered — a key of the feature's dictionary; empty when it is. */
  reason: string
  reason_params: Record<string, string>
  /** The conflict and the choice an «update» of this one needs. */
  requires: { id: string; choice: TransferChoice } | null
  dates: { local: TransferSide; archive: TransferSide }
}

export interface TransferRecoded {
  entity: string
  title: string
  from: string
  /** Empty while the new code is not given yet — it is, when the import is applied. */
  to: string
}

export interface TransferArchive {
  file_name: string
  size: number
  created_at: string
  app_version: string
  format_version: number
  /** The archive was taken from THIS installation. */
  same_install: boolean
}

export interface TransferPlanBase {
  archive: TransferArchive
  conflicts: TransferConflict[]
  notices: { recoded: TransferRecoded[]; dangling_refs: string[] }
  plan_token: string
}

export interface TransferUpload {
  upload_id: string
  file_name: string
  size: number
}

const SIZE_UNITS = ['byte', 'kilobyte', 'megabyte', 'gigabyte'] as const

/** A size worded by the interface language — «1,5 КБ», «1.5 kB» — as the files section words it. */
export function sizeText(bytes: number | null | undefined, locale: string): string {
  if (bytes === null || bytes === undefined) return ''
  let value = bytes
  let unit = 0
  while (value >= 1024 && unit < SIZE_UNITS.length - 1) {
    value /= 1024
    unit += 1
  }
  return new Intl.NumberFormat(locale, {
    style: 'unit',
    unit: SIZE_UNITS[unit],
    unitDisplay: 'short',
    maximumFractionDigits: unit === 0 ? 0 : 1,
  }).format(value)
}

/** The choices that are not the person's to make: a conflict with one option has it already. */
export function presetChoices(conflicts: TransferConflict[]): Record<string, TransferChoice> {
  const preset: Record<string, TransferChoice> = {}
  for (const conflict of conflicts) {
    if (conflict.options.length === 1) preset[conflict.id] = conflict.options[0]
  }
  return preset
}

/** «Update» is possible only while what it requires holds. */
export function canUpdate(conflict: TransferConflict, choices: Record<string, TransferChoice>): boolean {
  if (!conflict.options.includes('update')) return false
  if (!conflict.requires) return true
  const required = choices[conflict.requires.id]
  return required === undefined || required === conflict.requires.choice
}

/**
 * Set one choice and keep the rest consistent: a dependent «update» whose requirement is no longer
 * met falls back to «replace» — the only thing left to it.
 */
export function choose(
  conflicts: TransferConflict[],
  choices: Record<string, TransferChoice>,
  id: string,
  value: TransferChoice,
): Record<string, TransferChoice> {
  const next = { ...choices, [id]: value }
  let changed = true
  while (changed) {
    changed = false
    for (const conflict of conflicts) {
      if (next[conflict.id] === 'update' && !canUpdate(conflict, next)) {
        next[conflict.id] = 'replace'
        changed = true
      }
    }
  }
  return next
}

/** Every conflict to one choice where it is possible, to «replace» where it is not. */
export function chooseAll(conflicts: TransferConflict[], value: TransferChoice): Record<string, TransferChoice> {
  let next: Record<string, TransferChoice> = {}
  for (const conflict of conflicts) {
    next = choose(conflicts, next, conflict.id, conflict.options.includes(value) ? value : 'replace')
  }
  return next
}

/** Keep the choices of a new plan where the same conflict offers the same option. */
export function carriedChoices(
  conflicts: TransferConflict[],
  previous: Record<string, TransferChoice>,
): Record<string, TransferChoice> {
  let next = presetChoices(conflicts)
  for (const conflict of conflicts) {
    const kept = previous[conflict.id]
    if (kept && conflict.options.includes(kept) && next[conflict.id] === undefined) {
      next = choose(conflicts, next, conflict.id, kept)
    }
  }
  return next
}

export function allChosen(conflicts: TransferConflict[], choices: Record<string, TransferChoice>): boolean {
  return conflicts.every((conflict) => choices[conflict.id] !== undefined)
}
