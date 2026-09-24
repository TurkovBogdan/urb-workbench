// Ряд задач и перестановка в нём — арифметика, общая для всех мест, где задачи двигают руками.
//
// Вынесена из стора списка потому, что тем же рядом живёт и ветка на странице задачи, и два
// экземпляра одного правила разошлись бы на первой же правке. Правило повторяет бэк
// (`crud/link.py::link_reorder`): числа на экране обязаны совпасть с теми, что придут после
// сверки, иначе сверка перерисовывает строки, которые и так стоят на своих местах.
import type { TaskListRow } from './api'
import { SORT_STEP } from './labels'

/** Порядок строк так, как его отдаёт бэк (`api.py::_rows`): больший `sort` выше, дальше по времени и коду. */
export function byListOrder(left: TaskListRow, right: TaskListRow): number {
  return (
    right.sort - left.sort ||
    (left.created_at < right.created_at ? -1 : left.created_at > right.created_at ? 1 : 0) ||
    (left.code < right.code ? -1 : 1)
  )
}

/** Дети каждой задачи в порядке выдачи — индекс на одну сборку дерева, а не поиск по списку. */
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

/** Куда переезжает задача: ключа нет — поле не трогаем, `null` — снять группу или родителя. */
export interface MovePlace {
  group?: string | null
  parent?: string | null
}

/**
 * Набор задач после перемещения — до ответа бэка.
 *
 * Ряд соседей — дети родителя, у корня — задачи его группы; вставка после названного соседа,
 * перенумерация ряда сверху вниз с шагом бэка.
 *
 * Сосед не из этого ряда (так бывает, если список устарел) — `null`, и набор не трогают:
 * выдумывать место хуже, чем дождаться ответа.
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
