import { computed, ref, watch } from 'vue'
import { defineStore } from 'pinia'

import { listGroups, reorderGroup, restoreGroup, type GroupListRow } from '../api'
import { useWorkspaceContextStore } from '@/features/workspace/stores/workspace-context.store'
import { useListReorder } from '@/composables/useListReorder'

// Groups of the CURRENT workspace: the section is bound to the context selected in the sidebar and
// has no workspace switcher of its own — a second choice of the same thing would diverge from the
// first.
//
// A workspace switch re-reads the list by itself: the page does not know about it, otherwise every
// place that shows groups would have to remember about the switch.
//
// Showing deleted is a re-request, not a mask over what is loaded: without the flag deleted groups
// do not come from the backend at all, so there would be nothing to filter on the client.
export const useGroupsStore = defineStore('tasks-groups', () => {
  const context = useWorkspaceContextStore()

  const items = ref<GroupListRow[]>([])
  const loading = ref(true)
  const error = ref<unknown>(null)
  const includeDeleted = ref(false)
  const query = ref('')

  const workspace = computed(() => context.current)
  const noWorkspace = computed(() => context.loaded && !context.currentWorkspace)
  const isEmpty = computed(() => items.value.length === 0)

  // Search is client-side: a workspace has only a handful of groups, all already loaded. It
  // matches name and description case-insensitively; `toLocaleLowerCase` folds Cyrillic too.
  const visible = computed(() => {
    const needle = query.value.trim().toLocaleLowerCase()
    if (!needle) return items.value
    return items.value.filter((group) =>
      `${group.title}\n${group.description}`.toLocaleLowerCase().includes(needle),
    )
  })
  /** Groups exist, but the search left none. */
  const isFilteredOut = computed(() => !isEmpty.value && visible.value.length === 0)

  async function load() {
    // The workspace set may not be loaded yet: the section is also opened via a direct link, not
    // only by navigating from the sidebar.
    await context.ensure()

    const code = workspace.value
    if (!code) {
      items.value = []
      loading.value = false
      return
    }

    error.value = null
    try {
      // `report: false` — a failed section read is shown by the page itself (SectionError);
      // a toast on top would be a second message about the same thing.
      items.value = await listGroups(
        { workspace: code, include_deleted: includeDeleted.value },
        { report: false },
      )
    } catch (e) {
      error.value = e
      items.value = []
    } finally {
      loading.value = false
    }
  }

  watch(workspace, () => { void load() })

  function showDeleted(enabled: boolean) {
    includeDeleted.value = enabled
    return load()
  }

  // Restore is the only action without its own dialog: it is reversible (the "Delete" button is on
  // the same card), and a confirmation would be a question about nothing. A refusal is shown by the
  // client's toast; the list is re-read anyway — drift from the database is the usual reason for a
  // refusal.
  async function restore(code: string) {
    try {
      await restoreGroup(code)
    } catch {
      // The toast has already reported the refusal.
    }
    await load()
  }

  // ── Reordering by dragging ──────────────────────────────────────────────────

  // Only the whole live list can be reordered: on a narrowed one (search, trash shown) a drop
  // between two visible rows does not say where the group goes among the hidden ones, and a deleted
  // group has no place in the numbering at all. The order is the same one the task list's group
  // cards stand in.
  const reorderable = computed(() => !query.value.trim() && !includeDeleted.value)

  const { move, moving } = useListReorder({ items, request: reorderGroup, reload: load })

  return {
    items,
    visible,
    query,
    loading,
    error,
    includeDeleted,
    isEmpty,
    isFilteredOut,
    noWorkspace,
    reorderable,
    moving,
    load,
    showDeleted,
    restore,
    move,
  }
})
