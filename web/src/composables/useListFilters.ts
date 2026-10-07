import { computed, onBeforeUnmount, reactive, toValue, type ComputedRef, type MaybeRefOrGetter } from 'vue'
import { useRoute } from 'vue-router'

import type { AppliedFilter } from '@/components/FilterPanel.vue'
import type { TablerIcon } from '@/shared/nav'

export interface ListFilterOption {
  title: string
  value: string
  /** A second line of the item in the dropdown. */
  subtitle?: string
}

/**
 * A schema entry. `key` is both the address parameter and the request parameter: a bookmark or a
 * shared link opens the same selection. `disabledWhen` is a function rather than a flag — the
 * schema is computed before the filters it refers to exist.
 */
interface ListFilterBase {
  key: string
  label: string
  disabledWhen?: (filters: ListFilters) => boolean
}

export type ListFilterDef =
  | (ListFilterBase & { kind: 'search' })
  | (ListFilterBase & { kind: 'select'; options: ListFilterOption[] })
  | (ListFilterBase & { kind: 'toggle'; icon: TablerIcon })

export interface ListFilters {
  defs: ComputedRef<ListFilterDef[]>
  /** Search and select values as chips. Toggles are not here: the pressed button already says it. */
  applied: ComputedRef<AppliedFilter[]>
  /** Something to reset — a chip or a pressed toggle. */
  resettable: ComputedRef<boolean>
  /** As typed, untrimmed — otherwise the caret would jump on a space. */
  input: (key: string) => string
  text: (key: string) => string
  select: (key: string) => string | null
  flag: (key: string) => boolean
  set: (key: string, value: string | boolean | null) => void
  remove: (key: string) => void
  clear: () => void
  toQuery: () => Record<string, string>
}

/** Search runs as you type; without a pause it would send a request per letter. */
export const SEARCH_DELAY = 350

const FLAG_ON = '1'

/**
 * List filters from a schema: state, applied chips, the address and the search pause. The page
 * describes its filters and gets `onChange` once per effective change — it re-reads the list there.
 */
export function useListFilters(schema: MaybeRefOrGetter<ListFilterDef[]>, onChange: () => void): ListFilters {
  const route = useRoute()

  const defs = computed(() => toValue(schema))

  // An empty string is "not set" for every kind: search, select and toggle share one "off".
  const values = reactive<Record<string, string>>({})

  let searchTimer: ReturnType<typeof setTimeout> | null = null

  function stopSearchTimer(): void {
    if (searchTimer !== null) {
      clearTimeout(searchTimer)
      searchTimer = null
    }
  }

  onBeforeUnmount(stopSearchTimer)

  // The initial state comes from the address: coming "back" from a detail page keeps the selection.
  // Values are not validated here — the backend rejects garbage.
  for (const def of defs.value) {
    const raw = route.query[def.key]
    values[def.key] = typeof raw === 'string' ? raw : ''
  }

  function defOf(key: string): ListFilterDef | undefined {
    return defs.value.find((def) => def.key === key)
  }

  function input(key: string): string {
    return values[key] ?? ''
  }

  function text(key: string): string {
    return input(key).trim()
  }

  function select(key: string): string | null {
    const value = values[key] ?? ''
    return value === '' ? null : value
  }

  function flag(key: string): boolean {
    return values[key] === FLAG_ON
  }

  function set(key: string, value: string | boolean | null): void {
    const def = defOf(key)
    if (def === undefined) return

    if (def.kind === 'toggle') values[key] = value === true ? FLAG_ON : ''
    else values[key] = typeof value === 'string' ? value : ''

    // Search waits for a pause in typing; everything else applies at once.
    stopSearchTimer()
    if (def.kind === 'search') {
      searchTimer = setTimeout(() => {
        searchTimer = null
        onChange()
      }, SEARCH_DELAY)
    } else {
      onChange()
    }
  }

  /** The chip label is the value itself: the search text or the option title. */
  function labelOf(def: ListFilterDef): string | null {
    if (def.kind === 'toggle') return null
    if (def.kind === 'search') return text(def.key) || null

    const value = select(def.key)
    if (value === null) return null
    return def.options.find((option) => option.value === value)?.title ?? value
  }

  const applied = computed<AppliedFilter[]>(() => {
    const items: AppliedFilter[] = []
    for (const def of defs.value) {
      const label = labelOf(def)
      if (label !== null) items.push({ key: def.key, label })
    }
    return items
  })

  const resettable = computed(() =>
    applied.value.length > 0 || defs.value.some((def) => def.kind === 'toggle' && flag(def.key)),
  )

  function remove(key: string): void {
    stopSearchTimer()
    values[key] = ''
    onChange()
  }

  function clear(): void {
    stopSearchTimer()
    for (const def of defs.value) values[def.key] = ''
    onChange()
  }

  /** Set filters for the address; empty ones are not written — the address is long enough. */
  function toQuery(): Record<string, string> {
    const query: Record<string, string> = {}
    for (const def of defs.value) {
      const value = def.kind === 'search' ? text(def.key) : (values[def.key] ?? '')
      if (value !== '') query[def.key] = value
    }
    return query
  }

  return { defs, applied, resettable, input, text, select, flag, set, remove, clear, toQuery }
}
