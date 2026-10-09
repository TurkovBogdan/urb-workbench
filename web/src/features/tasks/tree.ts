// A row of tasks and reordering within it — arithmetic shared by every place where tasks are
// moved by hand.
//
// Pulled out of the list store because the branch on the task page lives on the same kind of row,
// and two copies of one rule would diverge at the first edit. The rule mirrors the backend
// (`crud/link.py::link_reorder`): the numbers on screen must match the ones that arrive after
// reconciliation, otherwise reconciliation redraws rows that are already in place.
import type { TaskListRow } from './api'
import { SORT_STEP } from './labels'

/** Row order as the backend returns it (`api.py::_rows`): higher `sort` first, then time and code. */
export function byListOrder(left: TaskListRow, right: TaskListRow): number {
  return (
    right.sort - left.sort ||
    (left.created_at < right.created_at ? -1 : left.created_at > right.created_at ? 1 : 0) ||
    (left.code < right.code ? -1 : 1)
  )
}

/** Each task's children in output order — an index for one tree build, not a list scan. */
export function childrenIndex(items: TaskListRow[]): Map<string, TaskListRow[]> {
  const index = new Map<string, TaskListRow[]>()
  for (const task of items) {
    if (!task.parent_code) continue
    const bucket = index.get(task.parent_code)
    if (bucket) bucket.push(task)
    else index.set(task.parent_code, [task])
  }
  return index
}

/** Where the task moves: key absent — field untouched, `null` — clear the group or parent. */
export interface MovePlace {
  group?: string | null
  parent?: string | null
}

/**
 * The task set after a move — before the backend answers.
 *
 * The sibling row is the parent's children, or for a root task the tasks of its group; insert
 * after the named sibling, renumber the row top to bottom with the backend's step.
 *
 * A sibling not from this row (happens when the list is stale) — `null`, and the set is left
 * alone: inventing a position is worse than waiting for the answer.
 */
export function moveInRow(
  items: TaskListRow[],
  code: string,
  afterCode: string | null,
  place: MovePlace,
): TaskListRow[] | null {
  const moved = items.find((task) => task.code === code)
  if (!moved) return null
  const next: TaskListRow = {
    ...moved,
    ...('group' in place ? { group_code: place.group ?? null } : {}),
    ...('parent' in place ? { parent_code: place.parent ?? null } : {}),
  }
  const sibling = (task: TaskListRow) =>
    task.parent_code === next.parent_code &&
    (next.parent_code !== null || task.group_code === next.group_code)
  const row = items.filter((task) => task.code !== code && sibling(task)).sort(byListOrder)
  const at = afterCode === null ? 0 : row.findIndex((task) => task.code === afterCode) + 1
  if (afterCode !== null && at === 0) return null
  row.splice(at, 0, next)

  const top = row.length * SORT_STEP
  const renumbered = new Map(row.map((task, index) => [task.code, top - index * SORT_STEP]))
  return items
    .map((task) => {
      const base = task.code === code ? next : task
      const sort = renumbered.get(task.code)
      return sort === undefined ? base : { ...base, sort }
    })
    .sort(byListOrder)
}
