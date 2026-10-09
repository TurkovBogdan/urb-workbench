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
import { childrenIndex, moveInRow, type MovePlace } from '../tree'
import type { TaskNode } from './tasks.store'

// The branch under a task — on its page, in the same form as in the main list.
//
// A store of its own, not shared with the list: the branch is shown whole — finished subtasks
// included, there is no filter to bring them back — while the list hides finished work by default.
// The branch is assembled the same way as the list — from the
// workspace's flat list (`GET /tasks`): it already holds the parents and positions of all tasks,
// and a separate "task descendants" endpoint would partly duplicate it. Reordering uses the same
// row arithmetic (`tree.ts`) and the same chain: on screen at once, then in the database,
// reconciliation after the last response.
export const useTaskSubtreeStore = defineStore('tasks-task-subtree', () => {
  const rootCode = ref('')
  const workspace = ref('')
  /**
   * The task itself is in the trash: its branch went there with it (delete cascades), so the trash
   * is read — otherwise the branch would be empty. A live task's deleted subtasks are not shown.
   */
  const rootDeleted = ref(false)

  const items = ref<TaskListRow[]>([])
  const loading = ref(false)
  const error = ref<unknown>(null)

  /** Open a task's branch. Another task means another branch: the old rows go at once. */
  function open(code: string, workspaceCode: string, deleted: boolean): Promise<void> {
    if (code !== rootCode.value) {
      rootCode.value = code
      items.value = []
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
        { workspace: workspace.value, include_deleted: rootDeleted.value },
        { report: false },
      )
      if (pending === code) items.value = rows
    } catch (e) {
      if (pending === code) error.value = e
    } finally {
      if (pending === code) loading.value = false
    }
  }

  const childrenByParent = computed(() => childrenIndex(items.value))

  /** How many children each task has — for the row's counter button, as in the list. */
  const childCounts = computed(
    () => new Map([...childrenByParent.value].map(([code, children]) => [code, children.length])),
  )

  /** The branch under the task: child nodes, each with its own children. Depth counts from zero, like list roots. */
  const nodes = computed<TaskNode[]>(() => {
    const walk = (task: TaskListRow, depth: number, last: boolean): TaskNode => {
      const children = childrenByParent.value.get(task.code) ?? []
      return {
        task,
        depth,
        last,
        children: children.map((child, index) => walk(child, depth + 1, index === children.length - 1)),
      }
    }
    const top = childrenByParent.value.get(rootCode.value) ?? []
    return top.map((child, index) => walk(child, 0, index === top.length - 1))
  })

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
    rootCode, items, loading, error, rootDeleted, childCounts, nodes,
    open, load, reorder, remove, restore, setStatus,
  }
})
