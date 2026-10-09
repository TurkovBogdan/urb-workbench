import { computed, ref } from 'vue'
import { defineStore } from 'pinia'

import { persisted, strCodec } from '@/shared/utils/persisted'

import { listWorkspaces, type WorkspaceRow } from '../api'

/**
 * The current workspace: which one the person is working in right now.
 *
 * Separate from `workspaces.store` because the roles differ: that one holds the workspaces PAGE
 * (trash toggle, counters, restore) and lives its lifetime, while this is the context of the whole
 * app: it outlives pages, the sidebar needs it on any route, and it survives a tab reload.
 *
 * The set arrives here from two sides, as in the shelf catalogue: `adopt` — when the list has
 * already come to the page (no reason to ask the backend twice), `ensure` — when workspaces are
 * needed by a place that didn't load them (the sidebar at startup). `loaded` tells "not asked yet"
 * from "asked, and there are no workspaces": without it an empty set would be re-requested on every
 * show.
 *
 * Deleted ones get here by neither path: nobody works in the trash, and selecting a discarded
 * workspace would mean opening a context that no longer exists for the rest of the app.
 */

// A key in the style of its neighbours (`ui.sort.researches.by`): `ui.` — interface state that
// lives only in the browser, then the module and the value itself.
const STORAGE_KEY = 'ui.tasks.workspace'

/** Nothing selected: there are no workspaces at all, or the list hasn't arrived yet. */
const NOTHING = ''

export const useWorkspaceContextStore = defineStore('tasks-workspace-context', () => {
  const items = ref<WorkspaceRow[]>([])
  const loading = ref(false)
  const loaded = ref(false)

  // The default is empty, so someone who never chose has no key in storage: they get the first
  // workspace from the list, not from yesterday's entry (see `persisted`).
  const current = persisted(STORAGE_KEY, NOTHING, strCodec)
  // Codes went upper case; a selection saved before that would match nothing in the list and
  // `reconcile` would silently swap it for the first workspace. Fold it once, on load.
  current.value = current.value.toUpperCase()

  // One request for everyone: the sidebar and the page starting together await a shared one
  // rather than each sending its own.
  let inflight: Promise<void> | null = null

  const isEmpty = computed(() => loaded.value && !items.value.length)

  const currentWorkspace = computed<WorkspaceRow | null>(
    () => items.value.find((workspace) => workspace.code === current.value) ?? null,
  )

  /**
   * Reconcile the selection with the set: the saved code may be gone (the workspace was deleted in
   * another tab), or there may be no selection at all (first visit). Neither is a failure: silently
   * settle on the first available one, and on an empty set clear the selection.
   */
  function reconcile(): void {
    if (items.value.some((workspace) => workspace.code === current.value)) return
    current.value = items.value[0]?.code ?? NOTHING
  }

  /** The set came from outside (the workspaces page already loaded it). */
  function adopt(rows: WorkspaceRow[]): void {
    items.value = rows.filter((row) => row.deleted_at === null)
    loaded.value = true
    reconcile()
  }

  async function ensure(): Promise<void> {
    if (loaded.value) return
    if (inflight) return inflight
    loading.value = true
    inflight = (async () => {
      try {
        // `report: false` — a silent failure: the list loads in the background under a sidebar
        // control, and the person wouldn't connect a toast about it with what they are doing. The
        // "no workspaces" placeholder is more honest than a toast.
        adopt(await listWorkspaces({}, { report: false }))
      } catch {
        items.value = []
      } finally {
        loading.value = false
        inflight = null
      }
    })()
    return inflight
  }

  /**
   * Re-read the set even though it is loaded: a workspace may have been created elsewhere (another
   * tab, an agent over MCP), and the switcher asks each time it opens. A failure keeps what is
   * shown — a slightly old list is no reason to empty it under the person's pointer.
   */
  async function refresh(): Promise<void> {
    try {
      adopt(await listWorkspaces({}, { report: false }))
    } catch {
      // Silent for the same reason as `ensure`.
    }
  }

  /**
   * Switching workspaces is only a context switch: there is no navigation here and must not be,
   * the person stays exactly where they were.
   */
  function select(code: string): void {
    if (code === current.value) return
    current.value = code
  }

  return { items, loading, loaded, current, currentWorkspace, isEmpty, adopt, ensure, refresh, select }
})
