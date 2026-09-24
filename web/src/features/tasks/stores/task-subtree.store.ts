import { computed, ref } from 'vue'
import { defineStore } from 'pinia'

import { deleteTask, listTasks, reorderTask, restoreTask, type TaskListRow } from '../api'
import { isTerminal } from '../labels'
import { childrenIndex, moveInRow, type MovePlace } from '../tree'
import type { TaskNode } from './tasks.store'

// Ветка под задачей — на её странице, в том же виде, что в общем списке.
//
// Стор свой, а не общий со списком: поиск и переключатели здесь сужают ОДНУ ветку, и делить их
// со списком значило бы, что набранное на странице задачи сужает весь список, куда человек потом
// вернётся. Собирается ветка тем же путём, что и список, — из плоского списка пространства
// (`GET /tasks`): в нём уже лежат родители и места всех задач, и отдельная ручка «потомки задачи»
// повторяла бы его частью. Перестановка — та же арифметика ряда (`tree.ts`) и та же цепочка:
// сразу на экране, следом в базе, сверка после последнего ответа.
export const useTaskSubtreeStore = defineStore('tasks-task-subtree', () => {
  const rootCode = ref('')
  const workspace = ref('')
  /** Сама задача в корзине: живых потомков у неё не бывает (удаление каскадно), и прятать удалённых незачем. */
  const rootDeleted = ref(false)

  const items = ref<TaskListRow[]>([])
  const loading = ref(false)
  const error = ref<unknown>(null)

  // Умолчания — те же, что у списка: завершённое спрятано, корзина не запрошена.
  const query = ref('')
  const hideFinished = ref(true)
  const includeDeleted = ref(false)

  const deletedShown = computed(() => includeDeleted.value || rootDeleted.value)
  const searching = computed(() => query.value.trim() !== '')

  /**
   * Открыть ветку задачи. Другая задача — другая ветка: набранное и переключатели возвращаются к
   * умолчаниям, иначе поиск, оставленный на прошлой задаче, молча сузил бы эту.
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

  // Код ветки, которую сейчас ждём: ответ по прежней задаче не должен лечь на новую.
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

  /** Сколько детей у каждой задачи — для кнопки-счётчика строки, как в списке. */
  const childCounts = computed(
    () => new Map([...childrenByParent.value].map(([code, children]) => [code, children.length])),
  )

  function hasLiveDescendant(task: TaskListRow): boolean {
    return (childrenByParent.value.get(task.code) ?? []).some(
      (child) => !isTerminal(child.status) || hasLiveDescendant(child),
    )
  }

  /** Завершена и под ней нет живой работы — правило списка: иначе вместе с ней ушла бы открытая подзадача. */
  function finishedAndIdle(task: TaskListRow): boolean {
    if (!hideFinished.value || !isTerminal(task.status)) return false
    return !hasLiveDescendant(task)
  }

  /** Ветка под задачей: узлы детей, у каждого — свои дети. Глубина считается от нуля, как у корней списка. */
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
   * Совпадения поиска — плоским рядом в порядке ветки, как отфильтрованный список: подзадача,
   * попавшая под запрос, не должна пропадать вместе с родителем, который под него не попал.
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

  /** Под задачей нет ни одной подзадачи — даже спрятанной переключателями. */
  const isEmpty = computed(() => !(childrenByParent.value.get(rootCode.value)?.length))

  /** Подзадачи есть, но переключатели или поиск спрятали все. */
  const isFilteredOut = computed(
    () => !isEmpty.value && (searching.value ? matches.value.length === 0 : nodes.value.length === 0),
  )

  // Запросы перестановки идут цепочкой, в порядке жестов, — см. `tasks.store.ts::reorder`.
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
        () => undefined, // об отказе сказал тост клиента; ответ на него — сверка ниже
      )
      .then(async () => {
        movesInFlight -= 1
        if (movesInFlight === 0) await load()
      })
    return moveChain
  }

  /** Обе операции обратимы и спрашивать нечего; отказ озвучил тост, ответ на него — свежая ветка. */
  async function remove(code: string): Promise<void> {
    try {
      await deleteTask(code)
    } catch {
      // см. выше
    }
    await load()
  }

  async function restore(code: string): Promise<void> {
    try {
      await restoreTask(code)
    } catch {
      // см. выше
    }
    await load()
  }

  return {
    rootCode, items, loading, error, query, hideFinished, includeDeleted, rootDeleted,
    deletedShown, searching, childCounts, nodes, matches, isEmpty, isFilteredOut,
    open, load, showDeleted, reorder, remove, restore,
  }
})
