import { computed, ref } from 'vue'
import { defineStore } from 'pinia'

import { useWorkspaceContextStore } from '@/features/workspace/stores/workspace-context.store'

import {
  deleteCodex,
  listCodexes,
  listWorkspaceCodexes,
  mount,
  reorderWorkspaceCodex,
  restoreCodex,
  setAgentCanEdit,
  unmount,
  type CodexRow,
  type WorkspaceCodexRow,
} from '../api'

/** A codex in the list, with its state in the current workspace. */
export interface CodexListItem extends CodexRow {
  mounted: boolean
  agentCanEdit: boolean
}

/**
 * The available codexes: every codex, in the CURRENT workspace's order, and how each stands there.
 *
 * The order is the workspace's and covers every codex, switched on or off — switching one never
 * moves it (`codex/crud/mount.py`). The backend hands the list already ordered; the page only
 * narrows it. Without a workspace there is no order to show: the codexes come by the global list.
 */
export const useCodexListStore = defineStore('codex-list', () => {
  const context = useWorkspaceContextStore()

  const rows = ref<WorkspaceCodexRow[]>([])
  const showDeleted = ref(false)
  const loading = ref(false)
  const error = ref<unknown>(null)

  const workspace = computed(() => context.currentWorkspace?.code ?? '')

  const items = computed<CodexListItem[]>(() =>
    rows.value.map((row) => ({ ...row.codex, mounted: row.mounted, agentCanEdit: row.agent_can_edit })),
  )

  // ── Filters ─────────────────────────────────────────────────────────────────
  // Held here rather than in the panel, so a search survives leaving the page and coming back.
  const query = ref('')

  const visible = computed(() => {
    const needle = query.value.trim().toLocaleLowerCase()
    if (!needle) return items.value
    return items.value.filter((item) =>
      [item.title, item.segment, item.description].some((text) => text.toLocaleLowerCase().includes(needle)),
    )
  })

  /** A narrowed or trash-mixed list names no real place for a drop — the order is changed on the
   *  whole row of live codexes. */
  const reorderable = computed(
    () =>
      Boolean(workspace.value) && !query.value.trim() && !showDeleted.value,
  )

  async function load(): Promise<void> {
    loading.value = true
    error.value = null
    try {
      await context.ensure()
      rows.value = workspace.value
        ? await listWorkspaceCodexes(workspace.value, showDeleted.value, { report: false })
        : (await listCodexes(showDeleted.value, { report: false })).map((codex) => ({
            codex,
            mounted: false,
            agent_can_edit: false,
          }))
    } catch (e) {
      error.value = e
    } finally {
      loading.value = false
    }
  }

  async function setMounted(code: string, on: boolean): Promise<void> {
    if (!workspace.value) return
    await (on ? mount(workspace.value, code) : unmount(workspace.value, code))
    await load()
  }

  async function setLock(code: string, agentCanEdit: boolean): Promise<void> {
    if (!workspace.value) return
    await setAgentCanEdit(workspace.value, code, agentCanEdit)
    await load()
  }

  /** A codex dropped at `toIndex` of the whole list — turned into "after whom". */
  async function move(code: string, toIndex: number): Promise<void> {
    const order = rows.value.map((row) => row.codex.code).filter((c) => c !== code)
    const after = toIndex <= 0 ? null : order[Math.min(toIndex, order.length) - 1] ?? null
    await reorderWorkspaceCodex(workspace.value, code, after)
    await load()
  }

  async function remove(code: string): Promise<void> {
    await deleteCodex(code)
    await load()
  }

  async function restore(code: string): Promise<void> {
    await restoreCodex(code)
    await load()
  }

  return {
    items,
    visible,
    query,
    reorderable,
    showDeleted,
    loading,
    error,
    workspace,
    load,
    setMounted,
    setLock,
    move,
    remove,
    restore,
  }
})
