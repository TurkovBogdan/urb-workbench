// Task list search depth: which scopes the field toggles and how they map onto the store.
//
// The haystack is built in layers, not as a single depth. Title and goal are the base and always
// in the haystack: they are what names the task in the list, and a base you could switch off
// would mean a search that fails to find a task by its name. Everything else lives in bodies that
// the list row does not carry at all, and each layer is switched on separately — brief, plan with
// stages, journal.
//
// The keys match the store fields one to one, so the adapter between the `SearchField` set (an
// array of enabled keys) and the three flags boils down to an enumeration — and lives here, next
// to the scopes themselves, not in the panel markup.
import { computed, type WritableComputedRef } from 'vue'
import { IconClipboardText, IconListCheck, IconNotes } from '@tabler/icons-vue'

import type { SearchScope } from '@/components/SearchField.vue'

export const SCOPE_BRIEF = 'brief'
export const SCOPE_PLAN = 'plan'
export const SCOPE_JOURNAL = 'journal'

/** Enabled search scopes; with all off, the search covers only title and goal. */
export interface TaskSearchScopes {
  inBrief: boolean
  inPlan: boolean
  inJournal: boolean
}

export const NO_SCOPES: TaskSearchScopes = { inBrief: false, inPlan: false, inJournal: false }

export function anyScope(scopes: TaskSearchScopes): boolean {
  return scopes.inBrief || scopes.inPlan || scopes.inJournal
}

// For a single letter the backend would read every body in the workspace to return a junk
// answer, so the client does not call it — the same threshold as the deep search in the research
// registry.
export const MIN_DEEP_QUERY_LENGTH = 2

const SCOPE_ICONS = {
  [SCOPE_BRIEF]: IconClipboardText,
  [SCOPE_PLAN]: IconListCheck,
  [SCOPE_JOURNAL]: IconNotes,
}

/** The scope set for the field; labels come from the call site — the dictionary is the feature's. */
export function taskSearchScopes(label: (scope: string) => string): SearchScope[] {
  return Object.entries(SCOPE_ICONS).map(([key, icon]) => ({ key, icon, label: label(key) }))
}

export function taskScopesModel(
  scopes: () => TaskSearchScopes,
  apply: (next: TaskSearchScopes) => void,
): WritableComputedRef<string[]> {
  return computed({
    get: () => {
      const { inBrief, inPlan, inJournal } = scopes()
      return [
        ...(inBrief ? [SCOPE_BRIEF] : []),
        ...(inPlan ? [SCOPE_PLAN] : []),
        ...(inJournal ? [SCOPE_JOURNAL] : []),
      ]
    },
    set: (keys) =>
      apply({
        inBrief: keys.includes(SCOPE_BRIEF),
        inPlan: keys.includes(SCOPE_PLAN),
        inJournal: keys.includes(SCOPE_JOURNAL),
      }),
  })
}
