import { computed, ref, watch } from 'vue'
import { defineStore } from 'pinia'

import { DEFAULT_PAGE_SIZE } from '@/constants/pagination'

import {
  deleteTask,
  listGroups,
  listTasks,
  reorderTask,
  restoreTask,
  type GroupRow,
  type TaskListRow,
} from '../api'
import { useWorkspaceContextStore } from '@/features/workspace/stores/workspace-context.store'

/**
 * Строка списка: задача и её глубина в ветке. Ноль — верхний уровень, дальше подзадачи.
 *
 * Дерево разворачивается в плоский ряд ЗДЕСЬ, а не в разметке: рекурсивный компонент строки
 * ради отступа в 20px означал бы, что каждая строка знает про своих детей, — а знать ей нужно
 * ровно одно, на какой она глубине.
 */
export interface TaskRowNode {
  task: TaskListRow
  depth: number
  /** Последний ребёнок у своего родителя: по нему рисуется загиб направляющей, а не сквозная линия. */
  last: boolean
}

/**
 * Ветка: задача верхнего уровня и её строки — она сама плюс всё, что под ней.
 *
 * Строки сгруппированы веткой, а не лежат одним рядом, потому что перетаскивают именно ветку:
 * задача уезжает вместе со своими подзадачами, и им незачем быть отдельными соседями в разметке —
 * перестановка тогда рвала бы их от родителя.
 */
export interface TaskBranch {
  root: TaskListRow
  rows: TaskRowNode[]
}

/** Секция списка: группа, её задачи верхнего уровня и их ветки. */
export interface TaskSection {
  group: GroupRow | null
  tasks: TaskListRow[]
  branches: TaskBranch[]
}

/** Формат показа списка. Второй (доска) появится значением здесь, а не веткой в разметке. */
export type TaskListFormat = 'list'

/** Значение фильтра группы: `null` — все, `''` — только задачи вне групп (секция «Без группы»). */
export type GroupFilter = string | null

// Список задач ТЕКУЩЕГО пространства, разложенный по группам.
//
// Пространство стор не выбирает и не хранит — он читает его из контекста (`workspace-context`),
// который живёт в шапке боковой панели и переживает страницы. Поэтому и перезагрузка при смене
// пространства — обязанность стора, а не страницы: выбор меняют из панели, находясь на любом
// маршруте, и список, узнающий об этом только при следующем открытии, показывал бы чужие задачи.
//
// Группы приезжают вторым запросом, а не приклеены к задачам: секция нужна и пустая (группа
// заведена, задач в ней пока нет), а по одним только задачам такую группу не восстановить.
//
// ФИЛЬТРЫ ЖИВУТ ЗДЕСЬ, А НЕ В АДРЕСЕ. В адресе только открытая задача (`?task=…`): им делятся —
// «посмотри вот это». Набор фильтров — рабочая поза самого человека, а не то, что посылают
// другому, и вынеси мы его в адрес, каждая правка поля писала бы запись в историю браузера, и
// «назад» отматывало бы буквы в поиске вместо закрытия окна задачи.
//
// Сужает выборку клиент, а не бэк (кроме корзины). Список пространства приезжает целиком — в нём
// сотни строк, а не сотни тысяч, — и фильтр по уже полученному набору отвечает мгновенно и без
// круга по сети. Исключение — `include_deleted`: удалённых в ответе нет вовсе, и «показать» их
// нечем, кроме нового запроса.
export const useTasksStore = defineStore('tasks-tasks', () => {
  const context = useWorkspaceContextStore()

  const groups = ref<GroupRow[]>([])
  const items = ref<TaskListRow[]>([])
  const loading = ref(true)
  const error = ref<unknown>(null)

  // Не переживает перезагрузку вкладки намеренно — как и у пространств: «показать удалённые» это
  // разовый заход в корзину, а не режим работы.
  const includeDeleted = ref(false)

  const format = ref<TaskListFormat>('list')

  // ── Фильтры ─────────────────────────────────────────────────────────────────
  const query = ref('')
  const statusFilter = ref<string | null>(null)
  const priorityFilter = ref<string | null>(null)
  const typeFilter = ref<string | null>(null)
  const groupFilter = ref<GroupFilter>(null)

  const page = ref(1)
  const pageSize = ref(DEFAULT_PAGE_SIZE)

  /** Пространств нет вовсе — задачам просто негде лежать, и список тут ни при чём. */
  const noWorkspace = computed(() => context.loaded && !context.currentWorkspace)

  /**
   * Верхний уровень: задачи без родителя.
   *
   * Подзадача в общем списке стояла наравне с родителем, и одна и та же работа читалась дважды —
   * сверху «Оформить счета», следом «Оформить счета → шаблон письма». Ветку раскрывает карточка
   * родителя, а список отвечает на вопрос «что вообще есть», и повтор в нём — шум.
   */
  const roots = computed(() => items.value.filter((task) => task.parent_code === null))

  const hasActiveFilters = computed(
    () =>
      query.value.trim() !== '' ||
      statusFilter.value !== null ||
      priorityFilter.value !== null ||
      typeFilter.value !== null ||
      groupFilter.value !== null,
  )

  function matches(task: TaskListRow): boolean {
    const needle = query.value.trim().toLowerCase()
    if (needle && !task.title.toLowerCase().includes(needle)) return false
    if (statusFilter.value !== null && task.status !== statusFilter.value) return false
    if (priorityFilter.value !== null && task.priority !== priorityFilter.value) return false
    if (typeFilter.value !== null && task.type !== typeFilter.value) return false
    // Пустая строка — «только вне групп»: у секции «Без группы» кода нет, и спросить про неё
    // иначе нечем. `null` — фильтра нет вовсе.
    if (groupFilter.value !== null && (task.group_code ?? '') !== groupFilter.value) return false
    return true
  }

  /**
   * Что стоит на странице до разбивки.
   *
   * Без фильтров — верхний уровень: подзадачи приедут под своими родителями ветками, и считать
   * их страницами отдельно незачем. С фильтрами — ЛЮБЫЕ подходящие задачи, включая подзадачи, и
   * ветки при этом не рисуются: подзадача, попавшая под условие, не должна пропадать вместе с
   * родителем, который под него не попал, а показанная веткой — тянуть на экран весь свой род.
   */
  const filtered = computed(() =>
    (hasActiveFilters.value ? items.value : roots.value).filter(matches),
  )

  const total = computed(() => filtered.value.length)
  const pageCount = computed(() => Math.max(1, Math.ceil(total.value / pageSize.value)))

  /** Строки текущей страницы: раскладку по группам получают именно они, а не вся выдача. */
  const pageItems = computed(() => {
    const from = (page.value - 1) * pageSize.value
    return filtered.value.slice(from, from + pageSize.value)
  })

  const isEmpty = computed(() => items.value.length === 0)
  /**
   * Строк нет, но не потому, что задач нет: их спрятали фильтры — и ответ человеку другой.
   * Считаем по НАБРАННЫМ фильтрам, а не по «в базе что-то есть»: пустой список при снятых
   * фильтрах — это «заведите первую», и предлагать сбросить там нечего.
   */
  const isFilteredOut = computed(() => hasActiveFilters.value && total.value === 0)

  /**
   * Раскладка по группам: секция на КАЖДУЮ группу пространства плюс «Без группы».
   *
   * Пустые секции показываются, и это не украшение: задачу переносят перетаскиванием в чужую
   * карточку, а перенести её в группу, которой на экране нет, нечем. Значит пустая группа — это
   * цель жеста, и убери мы её — единственным способом разложить задачу осталась бы форма правки.
   * Стоят пустые ВНИЗУ и приглушены (это уже дело разметки): цель для переноса не должна спорить
   * за внимание с группами, в которых есть работа.
   *
   * «Без группы» стоит ПОСЛЕДНЕЙ и не по алфавиту: это не тема наравне с остальными, а остаток —
   * то, что ещё не разложено. Поставь мы его первым, каждый заход в список начинался бы с кучи
   * неразобранного, а названные группы — то, ради чего группы и заводят, — уезжали бы вниз. Она
   * же — цель «вынуть из группы», поэтому показывается и пустой.
   *
   * Исключение одно: ОТОБРАННАЯ группа показывается в одиночку. Человек сузил список до неё, и
   * соседние карточки — ровно то, что он попросил убрать с глаз.
   */
  const sections = computed<TaskSection[]>(() => {
    // Строк на странице нет — нет и секций: иначе под сообщением «задач пока нет» висел бы ещё и
    // полный набор пустых заголовков, и ответ на вопрос «что тут есть» читался бы дважды.
    if (!pageItems.value.length) return []
    const byGroup = new Map<string, TaskListRow[]>()
    const loose: TaskListRow[] = []
    for (const task of pageItems.value) {
      if (!task.group_code) {
        loose.push(task)
        continue
      }
      const bucket = byGroup.get(task.group_code)
      if (bucket) bucket.push(task)
      else byGroup.set(task.group_code, [task])
    }
    const picked = groupFilter.value !== null
    const filled: TaskSection[] = []
    const empty: TaskSection[] = []
    for (const group of groups.value) {
      const tasks = byGroup.get(group.code)
      if (tasks) filled.push({ group, tasks, branches: branchesOf(tasks) })
      else if (!picked) empty.push({ group, tasks: [], branches: [] })
    }
    const out = [...filled, ...empty]
    if (loose.length || !picked || !out.length) {
      out.push({ group: null, tasks: loose, branches: branchesOf(loose) })
    }
    return out
  })

  /** Дети каждой задачи в порядке выдачи — индекс на одну сборку дерева, а не поиск по списку. */
  const childrenByParent = computed(() => {
    const index = new Map<string, TaskListRow[]>()
    for (const task of items.value) {
      if (!task.parent_code) continue
      const bucket = index.get(task.parent_code)
      if (bucket) bucket.push(task)
      else index.set(task.parent_code, [task])
    }
    return index
  })

  /**
   * Корни секции → ветки: корень и следом его потомки с глубинами. Ветки раскрыты всегда —
   * подзадач у одной задачи единицы, и прятать их за раскрывашкой значило бы прятать ровно то,
   * ради чего дерево и показывают.
   *
   * С активными фильтрами ветки не строятся вовсе (см. `filtered`): на экране плоский список
   * совпадений, где родство ничего не добавляет.
   */
  function branchesOf(roots: TaskListRow[]): TaskBranch[] {
    if (hasActiveFilters.value) {
      return roots.map((task) => ({ root: task, rows: [{ task, depth: 0, last: true }] }))
    }

    return roots.map((root) => {
      const rows: TaskRowNode[] = []
      const walk = (task: TaskListRow, depth: number, last: boolean) => {
        rows.push({ task, depth, last })
        const children = childrenByParent.value.get(task.code) ?? []
        children.forEach((child, index) => walk(child, depth + 1, index === children.length - 1))
      }
      walk(root, 0, true)
      return { root, rows }
    })
  }

  async function load() {
    // Пространства могли ещё не приехать (заход по прямой ссылке на список): без них неизвестно
    // даже то, в каком пространстве спрашивать задачи.
    await context.ensure()
    const workspace = context.currentWorkspace?.code
    if (!workspace) {
      groups.value = []
      items.value = []
      error.value = null
      loading.value = false
      return
    }
    error.value = null
    try {
      // Оба запроса разом: заголовки секций и их содержимое — половины одного экрана, и ждать
      // их по очереди значило бы показать пустой список на время второго круга.
      // `report: false` — отказ чтения раздела показывает сама страница (SectionError).
      const [nextGroups, nextTasks] = await Promise.all([
        listGroups({ workspace }, { report: false }),
        listTasks({ workspace, include_deleted: includeDeleted.value }, { report: false }),
      ])
      groups.value = nextGroups
      items.value = nextTasks
    } catch (e) {
      error.value = e
    } finally {
      loading.value = false
    }
  }

  function showDeleted(enabled: boolean) {
    includeDeleted.value = enabled
    resetPage()
    return load()
  }

  /** Любая правка фильтра возвращает на первую страницу: пятая страница прежней выдачи пуста. */
  function resetPage() {
    page.value = 1
  }

  function clearFilters() {
    query.value = ''
    statusFilter.value = null
    priorityFilter.value = null
    typeFilter.value = null
    groupFilter.value = null
    resetPage()
  }

  // Страница могла уехать за конец выдачи: фильтр сузил список, пока человек стоял на третьей.
  watch(pageCount, (count) => {
    if (page.value > count) page.value = count
  })

  // Смена пространства — это другой список, а не другой фильтр: старые карточки убираются сразу,
  // чтобы на время запроса на экране не стояли задачи из пространства, которое уже не выбрано.
  // Фильтр группы снимается вместе с ними: группы у каждого пространства свои, и код чужой
  // группы оставил бы список пустым без видимой причины.
  watch(
    () => context.current,
    () => {
      groups.value = []
      items.value = []
      groupFilter.value = null
      resetPage()
      loading.value = true
      void load()
    },
  )

  /**
   * Мягкое удаление и восстановление — обе операции обратимы, поэтому спрашивать здесь нечего;
   * подтверждение остаётся у необратимого (карточка задачи).
   *
   * Отказ гасится: о нём уже сказал тост клиента, а вся оставшаяся реакция — перечитать список.
   * Отказ обычно и означает, что показанное разошлось с базой, и свежий список — это ответ.
   */
  async function remove(code: string) {
    try {
      await deleteTask(code)
    } catch {
      // см. выше
    }
    await load()
  }

  async function restore(code: string) {
    try {
      await restoreTask(code)
    } catch {
      // см. выше
    }
    await load()
  }

  /**
   * Перетащили строку: новое место среди соседей и, если её тянули в чужую карточку, новая
   * группа.
   *
   * Список перечитывается целиком, а не правится на месте: перестановка перенумеровывает ВЕСЬ ряд
   * соседей, и держать эту арифметику второй раз на клиенте значило бы разойтись с базой на
   * первом же несовпадении.
   */
  async function reorder(code: string, afterCode: string | null, groupCode?: string | null) {
    try {
      await reorderTask(code, {
        after_code: afterCode,
        ...(groupCode === undefined ? {} : { group_code: groupCode }),
      })
    } catch {
      // см. выше
    }
    await load()
  }

  return {
    groups, items, loading, error, includeDeleted, format,
    query, statusFilter, priorityFilter, typeFilter, groupFilter,
    page, pageSize,
    roots, filtered, total, pageCount, pageItems,
    isEmpty, isFilteredOut, hasActiveFilters, noWorkspace, sections,
    load, showDeleted, resetPage, clearFilters, remove, restore, reorder,
  }
})
