import { computed, ref, watch } from 'vue'
import { defineStore } from 'pinia'

import { DEFAULT_PAGE_SIZE } from '@/constants/pagination'

import {
  deleteTask,
  listGroups,
  listTasks,
  reorderGroup as reorderGroupRequest,
  reorderTask,
  restoreTask,
  searchTasks,
  type GroupRow,
  type TaskListRow,
} from '../api'
import { isTerminal } from '../labels'
import { byListOrder, childrenIndex, moveInRow, type MovePlace } from '../tree'
import { anyScope, MIN_DEEP_QUERY_LENGTH, NO_SCOPES, type TaskSearchScopes } from '../search'
import { useWorkspaceContextStore } from '@/features/workspace/stores/workspace-context.store'

/**
 * Узел ветки: задача, её глубина и её дети.
 *
 * Дерево остаётся деревом, а не разворачивается в плоский ряд, и причина в перетаскивании:
 * sortable заводится НА КОНТЕЙНЕР, а ряд соседей у подзадачи — дети её родителя. Плоский список
 * строк такого контейнера не даёт вовсе, поэтому переставить подзадачу среди сестёр было нечем.
 *
 * `depth` и `last` остаются здесь, а не считаются разметкой: по ним рисуется отступ и загиб
 * направляющей, и строке по-прежнему не нужно знать ничего, кроме своего места.
 */
export interface TaskNode {
  task: TaskListRow
  depth: number
  /** Последний ребёнок у своего родителя: по нему рисуется загиб направляющей, а не сквозная линия. */
  last: boolean
  children: TaskNode[]
}

/** Секция списка: группа, её задачи верхнего уровня и их ветки. */
export interface TaskSection {
  group: GroupRow | null
  tasks: TaskListRow[]
  /** Ветки секции: по узлу на каждую задачу верхнего уровня, дети — внутри узла. */
  branches: TaskNode[]
}

/** Формат показа списка. Второй (доска) появится значением здесь, а не веткой в разметке. */
export type TaskListFormat = 'list'

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
  // Статус — НАБОР, приоритет — одно значение. Разница не в прихоти: «покажи работу и проверки» —
  // обычная поза, а «покажи горящее и замороженное разом» не значит ничего.
  const statusFilter = ref<string[]>([])
  const priorityFilter = ref<string | null>(null)
  // Фильтров группы и типа нет. Группы список и так показывает карточками, и каждую можно свернуть;
  // тип же меняет только набор полей на странице задачи и в списке не отвечает ни на один вопрос,
  // ради которого его сужают.

  // Завершённое спрятано УМОЛЧАНИЕМ, а не фильтром: список отвечает на вопрос «что делать», и
  // сделанное в этом ответе только занимает место. Поэтому же оно не входит в `clearFilters` как
  // «показать всё» — сброс возвращает умолчание, а не снимает его.
  const hideFinished = ref(true)

  // Явный выбор статуса сильнее умолчания: человек, отметивший «Выполнено», получил бы пустой
  // список, если бы скрытие продолжало работать поверх его выбора.
  const hideFinishedApplies = computed(
    () => hideFinished.value && !statusFilter.value.some(isTerminal),
  )

  // ── Глубина поиска ──────────────────────────────────────────────────────────
  // Заголовок и цель ищутся здесь же, по уже приехавшему списку. Постановки, плана и журнала в
  // строке нет вовсе — за них отвечает ручка поиска, и она возвращает только коды: пересечение
  // с уже имеющимся списком дешевле второй копии тех же карточек.
  const searchScopes = ref<TaskSearchScopes>({ ...NO_SCOPES })
  /** Коды из последнего глубокого запроса; `null` — его не было (нет запроса или областей). */
  const deepCodes = ref<Set<string> | null>(null)

  const page = ref(1)
  const pageSize = ref(DEFAULT_PAGE_SIZE)

  // ── Свёрнутые группы ────────────────────────────────────────────────────────
  // Карта ЯВНЫХ решений человека по карточкам групп и по веткам задач — одна на обе, потому что
  // коды групп (`GROUP@…`) и задач (`TASK@…`) не пересекаются. «Без группы» держит пустую строку —
  // ровно так же, как фильтр группы. Чего в карте нет, то решает умолчание: пустая группа приходит
  // свёрнутой, ветка задачи — раскрытой.
  //
  // Умолчание считается на месте, а не проставляется записью каждой пустой карточке: иначе группу
  // пришлось бы разворачивать самим в тот момент, когда в неё перетащили первую задачу, — то есть
  // держать в двух местах правило, которое и так выражается одной строкой.
  //
  // Пока только на время жизни страницы: где это хранить между заходами — `TASK@de5205ec30`.
  const folded = ref<Record<string, boolean>>({})

  function isCollapsed(code: string | null, empty = false): boolean {
    return folded.value[code ?? ''] ?? empty
  }

  /** Свернуть или развернуть карточку группы. Новый объект, а не мутация: за ссылкой следят. */
  function toggleCollapsed(code: string | null, empty = false) {
    const key = code ?? ''
    folded.value = { ...folded.value, [key]: !isCollapsed(key, empty) }
  }

  // ── Жест в процессе ─────────────────────────────────────────────────────────
  // Строку сейчас держат в руке. Нужно тому, что должно на это время затихнуть: подсказки кнопок
  // и глифов, всплывающие под курсором, пока он едет над строками, — жест они не поясняют, а
  // закрывают цель. Ставят и снимают флаг сами sortable (`TaskRows`, `TaskSubtree`).
  const dragging = ref(false)

  // Признак жеста вешается на `body`, а не на список: подсказки Vuetify телепортированы в корень
  // документа. Здесь, а не в компоненте списка, — строки перетаскивают и на странице задачи, и
  // признак нужен там же. Правило, которое по нему гасит подсказки, — в `styles/main.scss`.
  watch(dragging, (on) => document.body.classList.toggle('tasks-dragging', on))

  /**
   * Код последней задачи верхнего уровня группы — после неё встаёт брошенная на шапку карточки.
   *
   * Считается по ВСЕМ задачам стора, а не по странице: при разбивке на страницы последняя
   * строка карточки на экране — не последняя в ряду группы.
   */
  function lastRootOf(group: string | null): string | null {
    const row = items.value
      .filter((task) => task.parent_code === null && task.group_code === group)
      .sort(byListOrder)
    return row.length ? row[row.length - 1].code : null
  }

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
      statusFilter.value.length > 0 ||
      priorityFilter.value !== null,
  )

  /**
   * Задача завершена И под ней не осталось живой работы.
   *
   * Второе условие — не украшение: спрятав выполненного родителя, мы унесли бы с экрана и
   * незакрытую подзадачу под ним (в списке она показывается веткой, а не сама по себе).
   */
  function finishedAndIdle(task: TaskListRow): boolean {
    if (!hideFinishedApplies.value || !isTerminal(task.status)) return false
    return !hasLiveDescendant(task)
  }

  function hasLiveDescendant(task: TaskListRow): boolean {
    return (childrenByParent.value.get(task.code) ?? []).some(
      (child) => !isTerminal(child.status) || hasLiveDescendant(child),
    )
  }

  function matches(task: TaskListRow): boolean {
    const needle = query.value.trim().toLowerCase()
    if (needle && !matchesQuery(task, needle)) return false
    if (statusFilter.value.length && !statusFilter.value.includes(task.status)) return false
    if (priorityFilter.value !== null && task.priority !== priorityFilter.value) return false
    if (finishedAndIdle(task)) return false
    return true
  }

  /**
   * Совпадение по запросу: основа — заголовок и цель, их видно в строке; глубже — коды из
   * ручки поиска. Одно ИЛИ другое: включённая область ничего не сужает, она добавляет стог.
   */
  function matchesQuery(task: TaskListRow, needle: string): boolean {
    if (task.title.toLowerCase().includes(needle)) return true
    if (task.description.toLowerCase().includes(needle)) return true
    return deepCodes.value?.has(task.code) ?? false
  }

  /**
   * Что стоит на странице до разбивки.
   *
   * Без фильтров — верхний уровень: подзадачи приедут под своими родителями ветками, и считать
   * их страницами отдельно незачем. С фильтрами — ЛЮБЫЕ подходящие задачи, включая подзадачи, и
   * ветки при этом не рисуются: подзадача, попавшая под условие, не должна пропадать вместе с
   * родителем, который под него не попал, а показанная веткой — тянуть на экран весь свой род.
   */
  const filtered = computed(() => {
    if (!hasActiveFilters.value) return roots.value.filter(matches)
    return items.value
      .filter(matches)
      .sort((left, right) => (layoutOrder.value.get(left.code) ?? 0) - (layoutOrder.value.get(right.code) ?? 0))
  })

  /**
   * Место каждой задачи в ПОЛНОЙ раскладке: группы по своему порядку, внутри группы — ряд
   * корней, под каждым корнем — его ветка сверху вниз.
   *
   * Нужно это плоской выдаче под фильтром. Сортировать её одним `sort`, как приходит с бэка,
   * нельзя: у корня это место в ряду СВОЕЙ группы (`crud/link.py::_siblings`), у подзадачи —
   * место среди детей своего родителя, и числа из разных рядов между собой не значат ничего.
   * Карточкам списка это безразлично — внутри карточки ряд один, — а одному ряду нет.
   *
   * Считается обходом, а не сравнением пар: порядок ветки — это обход дерева, и выразить его
   * функцией сравнения двух строк без общего предка всё равно не выйдет.
   */
  const layoutOrder = computed(() => {
    const index = new Map<string, number>()
    let place = 0
    const walk = (task: TaskListRow) => {
      index.set(task.code, place++)
      for (const child of childrenByParent.value.get(task.code) ?? []) walk(child)
    }
    const order = [...roots.value].sort(
      (left, right) =>
        groupRank(right.group_code) - groupRank(left.group_code) ||
        right.sort - left.sort ||
        (left.code < right.code ? -1 : 1),
    )
    order.forEach(walk)
    return index
  })

  /** Место группы в раскладке; «Без группы» — ниже всех названных, как и в секциях. */
  function groupRank(code: string | null): number {
    if (!code) return Number.NEGATIVE_INFINITY
    return groups.value.find((group) => group.code === code)?.sort ?? 0
  }

  const total = computed(() => filtered.value.length)
  const pageCount = computed(() => Math.max(1, Math.ceil(total.value / pageSize.value)))

  /** Строки текущей страницы: раскладку по группам получают именно они, а не вся выдача. */
  const pageItems = computed(() => {
    const from = (page.value - 1) * pageSize.value
    return filtered.value.slice(from, from + pageSize.value)
  })

  const isEmpty = computed(() => items.value.length === 0)

  /**
   * Умолчание прячет что-то ПРЯМО СЕЙЧАС — в пространстве есть завершённые задачи.
   *
   * Не то же самое, что «умолчание включено»: оно включено всегда, и считать по нему значило бы
   * объявлять пустое пространство «спрятанным фильтрами» — с кнопкой сброса, которая ничего не
   * меняет, потому что сброс возвращает ровно это же умолчание.
   */
  const finishedHidden = computed(
    () => hideFinishedApplies.value && items.value.some((task) => isTerminal(task.status)),
  )

  /**
   * Строк нет, но не потому, что задач нет: их спрятали фильтры — и ответ человеку другой.
   * Считаем по тому, что РЕАЛЬНО сужает выдачу: пустой список без единого фильтра — это
   * «заведите первую», и предлагать сбросить там нечего.
   */
  const isFilteredOut = computed(
    () => (hasActiveFilters.value || finishedHidden.value) && total.value === 0,
  )

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
   * Исключение — СУЖЕННАЯ выдача: отобранная группа показывается в одиночку, а при любом другом
   * наборе фильтров пустые секции уходят все. Человек ищет, а не раскладывает: цель для переноса
   * ему сейчас не нужна (веток с фильтрами не рисуют вовсе), и десяток пустых карточек вокруг
   * единственной находки — ровно то, что он просил убрать с глаз.
   *
   * Порядок: сначала группы с задачами, следом «Без группы» — если в ней что-то лежит, — и только
   * потом пустые. Неразложенное — это работа, и стоять ниже пустых целей для переноса она не
   * должна; пустой же остаток возвращается в самый низ, к таким же пустым.
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
    const picked = hasActiveFilters.value
    const filled: TaskSection[] = []
    const empty: TaskSection[] = []
    for (const group of groups.value) {
      const tasks = byGroup.get(group.code)
      if (tasks) filled.push({ group, tasks, branches: branchesOf(tasks) })
      else if (!picked) empty.push({ group, tasks: [], branches: [] })
    }
    const unfiled: TaskSection = { group: null, tasks: loose, branches: branchesOf(loose) }
    const out = [...filled]
    if (loose.length) out.push(unfiled)
    out.push(...empty)
    // Пустой остаток — такая же цель для переноса, как пустая группа, и место ему там же, внизу.
    if (!loose.length && (!picked || !out.length)) out.push(unfiled)
    return out
  })

  const childrenByParent = computed(() => childrenIndex(items.value))

  /**
   * Корни секции → ветки: корень и следом его потомки с глубинами. Ветки раскрыты всегда —
   * подзадач у одной задачи единицы, и прятать их за раскрывашкой значило бы прятать ровно то,
   * ради чего дерево и показывают.
   *
   * С активными фильтрами ветки не строятся вовсе (см. `filtered`): на экране плоский список
   * совпадений, где родство ничего не добавляет.
   */
  function branchesOf(roots: TaskListRow[]): TaskNode[] {
    const walk = (task: TaskListRow, depth: number, last: boolean): TaskNode => {
      // С фильтрами ветка обрывается на корне: на экране плоский список совпадений.
      if (hasActiveFilters.value) return { task, depth, last, children: [] }
      // Скрытое умолчанием прячется и внутри ветки, иначе выполненная подзадача исчезала бы
      // из списка верхнего уровня и оставалась под родителем — одна задача в двух состояниях.
      // Вместе с ней уходит и всё под ней: живого там нет по самому условию.
      const children = (childrenByParent.value.get(task.code) ?? []).filter(
        (child) => !finishedAndIdle(child),
      )
      return {
        task,
        depth,
        last,
        children: children.map((child, index) =>
          walk(child, depth + 1, index === children.length - 1),
        ),
      }
    }
    return roots.map((root) => walk(root, 0, true))
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

  /**
   * Снять умолчание.
   *
   * Отдельно от `clearFilters`, потому что это его противоположность: сброс возвращает умолчание,
   * а здесь его как раз выключают — иначе из выдачи, спрятанной умолчанием, выхода бы не было.
   */
  function showFinished() {
    hideFinished.value = false
    resetPage()
  }

  function clearFilters() {
    query.value = ''
    statusFilter.value = []
    priorityFilter.value = null
    searchScopes.value = { ...NO_SCOPES }
    // Скрытие завершённого возвращается ВКЛЮЧЁННЫМ: это умолчание списка, а не набранный фильтр,
    // и «сбросить всё» означает вернуться к обычному виду, а не показать вообще всё.
    hideFinished.value = true
    resetPage()
  }

  // ── Глубокий поиск ──────────────────────────────────────────────────────────

  let deepTimer: ReturnType<typeof setTimeout> | undefined
  /** Номер последнего запроса: ответ на отменённый набор приходит позже и затирал бы свежий. */
  let deepRun = 0

  async function runDeepSearch() {
    const needle = query.value.trim()
    const workspace = context.currentWorkspace?.code
    if (!workspace || !anyScope(searchScopes.value) || needle.length < MIN_DEEP_QUERY_LENGTH) {
      deepCodes.value = null
      return
    }
    const run = ++deepRun
    try {
      const codes = await searchTasks(
        {
          workspace,
          query: needle,
          in_brief: searchScopes.value.inBrief,
          in_plan: searchScopes.value.inPlan,
          in_journal: searchScopes.value.inJournal,
        },
        { report: false },
      )
      if (run === deepRun) deepCodes.value = new Set(codes)
    } catch {
      // Отказ глубокого поиска не гасит выдачу: основа (заголовок и цель) ищется на месте и
      // продолжает работать, а тост о сбое покажет клиент.
      if (run === deepRun) deepCodes.value = null
    }
  }

  /**
   * Запрос придержан: глубокий поиск читает тела всего пространства, и посылать его на каждую
   * букву значило бы платить за набор слова шестью запросами подряд.
   */
  function scheduleDeepSearch() {
    clearTimeout(deepTimer)
    deepTimer = setTimeout(() => void runDeepSearch(), 250)
  }

  watch([query, searchScopes], scheduleDeepSearch, { deep: true })

  // Страница могла уехать за конец выдачи: фильтр сузил список, пока человек стоял на третьей.
  watch(pageCount, (count) => {
    if (page.value > count) page.value = count
  })

  // Смена пространства — это другой список, а не другой фильтр: старые карточки убираются сразу,
  // чтобы на время запроса на экране не стояли задачи из пространства, которое уже не выбрано.
  watch(
    () => context.current,
    () => {
      groups.value = []
      items.value = []
      // Коды глубокого поиска и свёрнутых карточек — из прежнего пространства: в новом они
      // ничему не соответствуют.
      deepCodes.value = null
      folded.value = {}
      resetPage()
      loading.value = true
      void load()
      void runDeepSearch()
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
   * Перетащили карточку группы: рядом с какой она теперь стоит.
   *
   * Позиция названа соседкой (`after` — встать под ней, `before` — над ней), потому что `sort` на
   * экране не виден вовсе. Список перечитывается целиком, как и после перестановки задачи: ряд
   * перенумеровывается на бэке, и вторая копия этой арифметики здесь разошлась бы с базой.
   *
   * Порядок секций на экране при этом не повторяет `sort` буквально — пустые группы уходят вниз
   * (см. `sections`), поэтому перенос пустой карточки вверх сохранится, но её места не изменит.
   */
  async function reorderGroup(code: string, place: { after?: string | null; before?: string | null }) {
    try {
      await reorderGroupRequest(code, {
        ...(place.after !== undefined ? { after_code: place.after } : {}),
        ...(place.before !== undefined ? { before_code: place.before } : {}),
      })
    } catch {
      // см. ниже: об отказе уже сказал тост клиента, а ответ на него — свежий список.
    }
    await load()
  }

  // ── Перестановка задач: сразу на экране, следом в базе ───────────────────────

  /** Применить перемещение к задачам стора — до ответа бэка (правило ряда — `tree.ts::moveInRow`). */
  function applyMove(code: string, afterCode: string | null, place: MovePlace) {
    const next = moveInRow(items.value, code, afterCode, place)
    if (next) items.value = next
  }

  // Запросы перестановки идут ЦЕПОЧКОЙ, в порядке жестов: два быстрых броска подряд иначе ушли бы
  // параллельно, и бэк мог бы применить их в обратном порядке.
  let moveChain: Promise<void> = Promise.resolve()
  let movesInFlight = 0

  /**
   * Перетащили строку: новое место среди соседей, а если её тянули в чужую карточку или из ветки
   * наверх — ещё и новая группа и новый родитель.
   *
   * Порядок действий: стор меняется сразу, запрос уходит следом, список перечитывается после
   * ответа. Раньше было наоборот — и полсекунды строка стояла на старом месте: библиотека
   * откатывает перестановку в DOM ещё до `onEnd`, а новый порядок появлялся только после
   * перечитки. Перечитка осталась, но теперь это сверка: если бэк согласен, на экране не меняется
   * ничего, а если нет (отказ, устаревший список) — побеждает бэк.
   *
   * Перечитывается один раз, когда цепочка опустела: ответ на первый из двух жестов, пришедший
   * посреди второго, откатил бы второй на экране.
   */
  function reorder(
    code: string,
    afterCode: string | null,
    place: MovePlace = {},
  ): Promise<void> {
    applyMove(code, afterCode, place)
    movesInFlight += 1
    moveChain = moveChain
      .then(() =>
        reorderTask(code, {
          after_code: afterCode,
          // Ключа нет — поле не трогаем; `null` — снять группу или открепить от родителя. Различие
          // выражается наличием ключа, и здесь оно ровно такое же, как в теле запроса.
          ...('group' in place ? { group_code: place.group } : {}),
          ...('parent' in place ? { parent_code: place.parent } : {}),
        }),
      )
      .then(
        () => undefined,
        () => undefined, // об отказе уже сказал тост клиента; ответ на него — сверка ниже
      )
      .then(async () => {
        movesInFlight -= 1
        if (movesInFlight === 0) await load()
      })
    return moveChain
  }

  return {
    groups, items, loading, error, includeDeleted, format,
    query, statusFilter, priorityFilter,
    hideFinished, hideFinishedApplies, searchScopes,
    page, pageSize,
    roots, filtered, total, pageCount, pageItems,
    isEmpty, isFilteredOut, hasActiveFilters, finishedHidden, noWorkspace, sections,
    folded, isCollapsed, toggleCollapsed, dragging, lastRootOf,
    load, showDeleted, showFinished, resetPage, clearFilters, remove, restore, reorder,
    reorderGroup,
  }
})
