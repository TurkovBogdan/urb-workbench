import { computed, ref } from 'vue'
import { defineStore } from 'pinia'

import {
  listWorkspaces,
  reorderWorkspace,
  restoreWorkspace,
  type WorkspaceListRow,
} from '../api'
import { useWorkspaceContextStore } from './workspace-context.store'

// The tasks module's workspaces. The list is short and unpaginated (a workspace is the top level of
// the layout, they are created one at a time), and the backend sets the order — `sort`, then
// title. So the store never sorts; it searches what is already loaded and re-requests for the
// trash toggle — the same as the groups store.
//
// Showing deleted ones is a real re-request, not a mask over what's loaded: without the flag the
// backend doesn't send deleted ones at all, so there would be nothing to filter on the client.
//
// The fresh list is handed to the context (`workspace-context.store`): the page is the only place
// where workspaces are created, renamed and deleted, and there must be no second copy of the set
// living a life of its own — the sidebar selection updates from the same request as the cards.
export const useWorkspacesStore = defineStore('tasks-workspaces', () => {
  const context = useWorkspaceContextStore()
  const items = ref<WorkspaceListRow[]>([])
  const loading = ref(true)
  const error = ref<unknown>(null)

  // Deliberately does not survive a tab reload: "show deleted" is a one-off trip to the trash, not
  // a working mode, and a toggle stuck on would open the list every time mixed with what the
  // person already threw away.
  const includeDeleted = ref(false)
  const query = ref('')

  const isEmpty = computed(() => items.value.length === 0)

  // Search is client-side, as for groups: there are only a handful of workspaces, all already
  // loaded. It matches name and description case-insensitively; `toLocaleLowerCase` folds Cyrillic
  // too.
  const visible = computed(() => {
    const needle = query.value.trim().toLocaleLowerCase()
    if (!needle) return items.value
    return items.value.filter((workspace) =>
      `${workspace.title}\n${workspace.description}`.toLocaleLowerCase().includes(needle),
    )
  })
  /** Workspaces exist, but the search left none. */
  const isFilteredOut = computed(() => !isEmpty.value && visible.value.length === 0)

  async function load() {
    error.value = null
    try {
      // `report: false` — a failure to read the section is shown by the page itself (SectionError);
      // a toast on top would be a second message about the same thing.
      items.value = await listWorkspaces(
        { include_deleted: includeDeleted.value },
        { report: false },
      )
      // The context filters out deleted ones itself: here they are a legitimate part of the list
      // (the trash toggle), there they are a workspace nobody can work in.
      context.adopt(items.value)
    } catch (e) {
      error.value = e
    } finally {
      loading.value = false
    }
  }

  function showDeleted(enabled: boolean) {
    includeDeleted.value = enabled
    return load()
  }

  // Restore is the only action without its own dialog: it is reversible (the "Delete" button that
  // undoes it sits on the same card), and asking for confirmation would be a question about
  // nothing. A failure here is shown by the client's toast — the card has no place of its own for
  // a message, so the exception is swallowed: nobody outside would catch it, and an unhandled
  // promise would end up in the console.
  //
  // Returns whether it worked: the "Restore" in the post-delete notification confirms success with
  // a toast of its own, and must not confirm a refusal.
  async function restore(code: string): Promise<boolean> {
    let restored = true
    try {
      await restoreWorkspace(code)
    } catch {
      // The toast already reported the failure. Reload the list anyway: a failure usually means
      // what is shown has drifted from the database, and a fresh list is the answer.
      restored = false
    }
    await load()
    return restored
  }

  // ── Reordering by dragging ──────────────────────────────────────────────────

  // Only the whole live list can be reordered: on a narrowed one (search, trash shown) a drop
  // between two visible rows does not say where the row goes among the hidden ones, and a deleted
  // row has no place in the numbering at all.
  const reorderable = computed(() => !query.value.trim() && !includeDeleted.value)

  // Requests go as a CHAIN, in gesture order: two quick drops must not race each other to the
  // backend and land in reverse.
  let moveChain: Promise<void> = Promise.resolve()
  let movesInFlight = 0

  /**
   * A row was dropped at `toIndex` of the list. On screen at once, then in the database.
   *
   * The library reverts its own DOM reorder before `onEnd` and lets Vue redraw from the array, so
   * without moving the row here first it would sit in its old place until the re-read. The re-read
   * still follows — once, when the chain has drained — as reconciliation: if the backend agrees,
   * nothing moves; if it refused (the toast says why) or the list was stale, the backend wins.
   */
  function move(code: string, toIndex: number) {
    const from = items.value.findIndex((workspace) => workspace.code === code)
    if (from < 0 || from === toIndex) return
    const next = [...items.value]
    const [row] = next.splice(from, 1)
    next.splice(toIndex, 0, row)
    items.value = next
    context.adopt(next)

    // The neighbour above names the place; at the very top there is none, so the one below does.
    const place = toIndex > 0
      ? { after_code: next[toIndex - 1].code }
      : { before_code: next[1].code }

    movesInFlight += 1
    moveChain = moveChain
      .then(() => reorderWorkspace(code, place))
      .then(() => undefined, () => undefined)
      .finally(() => {
        movesInFlight -= 1
        if (movesInFlight === 0) void load()
      })
  }

  return {
    items,
    visible,
    query,
    loading,
    error,
    includeDeleted,
    isEmpty,
    isFilteredOut,
    reorderable,
    load,
    showDeleted,
    restore,
    move,
  }
})
