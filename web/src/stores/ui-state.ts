import { defineStore } from 'pinia'
import { reactive } from 'vue'

import { persisted, strCodec } from '@/shared/utils/persisted'

// Interface state: how the person left a list when they walked away from it.
//
// A separate home from `settings`: there are the CHOICES, set up once and edited on the settings
// page; here is the trace of work that the person didn't configure but simply left behind. Keeping
// the sort order in the list's own store wasn't enough: it lives only until the tab reloads, and
// after that the list silently went back to its default.
//
// Values are stored as STRINGS and not validated here: each section's backend knows its set of
// sort keys, and the whitelist lives next to it (`features/*/api.ts`). The list's store repairs the
// value on read with its own `resolve*` — then a corrupted key in localStorage breaks one list, not
// the request.
export const useUiStateStore = defineStore('ui-state', () => {
  // The registry defaults to "recently updated first", not "when created": opening the registry,
  // people return to what they were working on, not to what they once created.
  const researchSort = reactive({
    by: persisted('ui.sort.researches.by', 'updated_at', strCodec),
    dir: persisted('ui.sort.researches.dir', 'desc', strCodec),
  })

  const groupSort = reactive({
    by: persisted('ui.sort.groups.by', 'research_updated_at', strCodec),
    dir: persisted('ui.sort.groups.dir', 'desc', strCodec),
  })

  return { researchSort, groupSort }
})
