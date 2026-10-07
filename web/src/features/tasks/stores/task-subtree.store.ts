import { computed, ref } from 'vue'
import { defineStore } from 'pinia'

import {
  deleteTask,
  listTasks,
  reorderTask,
  restoreTask,
  setTaskStatus,
  type TaskListRow,
} from '../api'
import { isTerminal } from '../labels'
import { childrenIndex, moveInRow, type MovePlace } from '../tree'
import type { TaskNode } from './tasks.store'

// The branch under a task — on its page, in the same form as in the main list.
//
// A store of its own, not shared with the list: search and toggles here narrow ONE branch, and
// sharing them with the list would mean that what is typed on the task page narrows the whole list
// the person later returns to. The branch is assembled the same way as the list — from the
// workspace's flat list (`GET /tasks`): it already holds the parents and positions of all tasks,
// and a separate "task descendants" endpoint would partly duplicate it. Reordering uses the same
// row arithmetic (`tree.ts`) and the same chain: on screen at once, then in the database,
// reconciliation after the last response.
export const useTaskSubtreeStore = defineStore('tasks-task-subtree', () => {
  const rootCode = ref('')
  const workspace = ref('')
  /** The task itself is in the trash: it has no live descendants (delete cascades), so no point hiding deleted. */
  const rootDeleted = ref(false)

  const items = ref<TaskListRow[]>([])
  const loading = ref(false)
  const error = ref<unknown>(null)

  // Same defaults as the list: finished hidden, trash not requested.
  const query = ref('')
  const hideFinished = ref(true)
  const includeDeleted = ref(false)

  const deletedShown = computed(() => includeDeleted.value || rootDeleted.value)
  const searching = computed(() => query.value.trim() !== '')

  /**
   * Open a task's branch. Another task means another branch: the query and toggles go back to
   * defaults, otherwise a search left over from the previous task would silently narrow this one.
   */
  function open(code: string, workspaceCode: string, deleted: boolean): Promise<void> {
    if (code !== rootCode.value) {
      rootCode.value = code
      items.value = []
      query.value = ''
      hideFinished.value = true
      includeDeleted.value = false
    }
    workspace.value = workspaceCode
    rootDeleted.value = deleted
    return load()
  }

  // Code of the branch we are waiting for: a response for the previous task must not land on the new one.
  let pending = ''

  async function load(): Promise<void> {
    if (!rootCode.value || !workspace.value) return
    const code = rootCode.value
    pending = code
    loading.value = true
    error.value = null
    try {
      const rows = await listTasks(
        { workspace: workspace.value, include_deleted: deletedShown.value },
        { report: false },
      )
      if (pending === code) items.value = rows
    } catch (e) {
      if (pending === code) error.value = e
    } finally {
      if (pending === code) loading.value = false
    }
  }

  function showDeleted(enabled: boolean): Promise<void> {
    includeDeleted.value = enabled
    return load()
  }

  const childrenByParent = computed(() => childrenIndex(items.value))

  /** How many children each task has — for the row's counter button, as in the list. */
  const childCounts = computed(
    () => new Map([...childrenByParent.value].map(([code, children]) => [code, children.length])),
  )

  function hasLiveDescendant(task: TaskListRow): boolean {
    return (childrenByParent.value.get(task.code) ?? []).some(
      (child) => !isTerminal(child.status) || hasLiveDescendant(child),
    )
  }

  /** Finished with no live work under it — the list's rule: otherwise an open subtask would vanish with it. */
  function finishedAndIdle(task: TaskListRow): boolean {
    if (!hideFinished.value || !isTerminal(task.status)) return false
    return !hasLiveDescendant(task)
  }

  /** The branch under the task: child nodes, each with its own children. Depth counts from zero, like list roots. */
  const nodes = computed<TaskNode[]>(() => {
    const walk = (task: TaskListRow, depth: number, last: boolean): TaskNode => {
      const children = visibleChildren(task.code)
      return {
        task,
        depth,
        last,
        children: children.map((child, index) => walk(child, depth + 1, index === children.length - 1)),
      }
    }
    const top = visibleChildren(rootCode.value)
    return top.map((child, index) => walk(child, 0, index === top.length - 1))
  })

  function visibleChildren(code: string): TaskListRow[] {
    return (childrenByParent.value.get(code) ?? []).filter((child) => !finishedAndIdle(child))
  }

  /**
   * Search matches as a flat row in branch order, like the filtered list: a subtask that matches
   * the query must not disappear along with a parent that does not.
   */
  const matches = computed<TaskListRow[]>(() => {
    const needle = query.value.trim().toLowerCase()
    const out: TaskListRow[] = []
    const walk = (code: string) => {
      for (const child of childrenByParent.value.get(code) ?? []) {
        const hit =
          child.title.toLowerCase().includes(needle) ||
          child.description.toLowerCase().includes(needle)
        if (hit && !finishedAndIdle(child)) out.push(child)
        walk(child.code)
      }
    }
    if (needle) walk(rootCode.value)
    return out
  })

  /** The task has no subtasks at all — not even ones hidden by the toggles. */
  const isEmpty = computed(() => !(childrenByParent.value.get(rootCode.value)?.length))

  /** Subtasks exist, but the toggles or the search hid all of them. */
  const isFilteredOut = computed(
    () => !isEmpty.value && (searching.value ? matches.value.length === 0 : nodes.value.length === 0),
  )

  // Reorder requests go as a chain, in gesture order — see `tasks.store.ts::reorder`.
  let moveChain: Promise<void> = Promise.resolve()
  let movesInFlight = 0

  function reorder(code: string, afterCode: string | null, place: MovePlace = {}): Promise<void> {
    const next = moveInRow(items.value, code, afterCode, place)
    if (next) items.value = next
    movesInFlight += 1
    moveChain = moveChain
      .then(() =>
        reorderTask(code, {
          after_code: afterCode,
          ...('group' in place ? { group_code: place.group } : {}),
          ...('parent' in place ? { parent_code: place.parent } : {}),
        }),
      )
      .then(
        () => undefined,
        () => undefined, // the client's toast reported the refusal; the answer is the re-read below
      )
      .then(async () => {
        movesInFlight -= 1
        if (movesInFlight === 0) await load()
      })
    return moveChain
  }

  /** The row has already asked where it should; a refusal was voiced by the toast, the answer is a fresh branch. */
  async function remove(code: string): Promise<void> {
    try {
      await deleteTask(code)
    } catch {
      // see above
    }
    await load()
  }

  async function restore(code: string): Promise<void> {
    try {
      await restoreTask(code)
    } catch {
      // see above
    }
    await load()
  }

  async function setStatus(code: string, status: string): Promise<void> {
    try {
      await setTaskStatus(code, status)
    } catch {
      // see above
    }
    await load()
  }

  return {
    rootCode, items, loading, error, query, hideFinished, includeDeleted, rootDeleted,
    deletedShown, searching, childCounts, nodes, matches, isEmpty, isFilteredOut,
    open, load, showDeleted, reorder, remove, restore, setStatus,
  }
})
