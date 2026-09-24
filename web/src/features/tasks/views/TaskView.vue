<script setup lang="ts">
// Задача целиком — СТРАНИЦА по адресу `/tasks/task/TASK@…`, а не окно поверх списка.
//
// Почему страницей. Задачу не столько просматривают, сколько в ней работают: правят текст, водят
// статус, заводят и открывают подзадачи. Окну для этого не хватало ни места (проза и колонка
// разметки делили ширину модалки), ни постоянства — оно закрывалось мимоходом. У страницы свой
// адрес, своя история переходов и вся ширина экрана.
//
// ПРАВКА ИДЁТ ЗДЕСЬ ЖЕ. Отдельной формы у задачи нет: поля правятся на месте и уезжают сами —
// текстовые после паузы в наборе и по уходу из поля, выбор и даты сразу по смене. Кнопки
// сохранения нет, и «отмены» тоже: единственное состояние задачи — то, что в базе. Уход со
// страницы дописывает набранное (`onBeforeRouteLeave`): переход не должен стоить последней фразы.
//
// Две колонки, и граница между ними смысловая. Слева то, что человек ЧИТАЕТ подряд, — описание,
// текст задачи, — и связи с соседними задачами: родитель сверху, подзадачи снизу. Справа то, чем
// задачу РАЗМЕЧАЮТ: статус, тип, приоритет, группа, срок и отметки времени.
//
// Рамка — общий `PageLayout` с общей шапкой страницы; колонки навигации, как у деталок
// исследования, здесь нет: у задачи нет длинного документа, по разделам которого стоило бы
// водить оглавлением, а выход наверх — это кнопка «назад» в шапке.
import { computed, onActivated, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { onBeforeRouteLeave, useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import {
  IconArchiveOff,
  IconArrowUp,
  IconCalendarEvent,
  IconDotsVertical,
  IconFlame,
  IconPlus,
  IconRefresh,
  IconTrash,
} from '@tabler/icons-vue'

import PageLayout from '@/layout/templates/PageLayout.vue'
import PageHeader from '@/layout/components/PageHeader.vue'
import ConfirmDialog from '@/components/ConfirmDialog.vue'
import CopyChip from '@/components/CopyChip.vue'
import { MarkdownEditor } from '@/components/markdown/editor'
import SectionError from '@/components/SectionError.vue'
import SectionHeader from '@/components/SectionHeader.vue'
import IconSwatch from '@/components/IconSwatch.vue'
import VSelectSearch from '@/components/VSelectSearch.vue'
import { useChangeSubscription } from '@/composables/useChangeSubscription'
import { fmtDateTime, fmtRelative } from '@/shared/utils/date'
import type { Change } from '@/stores/changes'

import TaskFieldConflictDialog from '../components/TaskFieldConflictDialog.vue'
import TaskFormDialog from '../components/TaskFormDialog.vue'
import TaskJournal from '../components/TaskJournal.vue'
import TaskPrioritySelect from '../components/TaskPrioritySelect.vue'
import TaskStages from '../components/TaskStages.vue'
import TaskStatusSelect from '../components/TaskStatusSelect.vue'
import TaskSubtasksPanel from '../components/TaskSubtasksPanel.vue'
import { listGroups, type GroupRow, type TaskDetail, type TaskListRow, type TaskUpdateBody } from '../api'
import { deadlineDay, formatDay, formatDeadline, parseDay } from '../dates'
import { TASK_BRIEF_FEATURES, TASK_DOCUMENT_FEATURES } from '../editor'
import {
  BODY_MAX,
  TASK_CONSTRAINTS_MAX,
  TASK_CONTEXT_MAX,
  TASK_CRITERIA_MAX,
  TASK_DESCRIPTION_MAX,
  TASK_TITLE_MAX,
  TASK_TYPES,
  typeLayout,
} from '../labels'
import { useTaskDetailStore } from '../stores/task-detail.store'

/** Тишина в поле, после которой набранное уезжает на бэк. */
const TYPING_PAUSE = 700

/** Имя своего маршрута: по нему отличается СВОЙ параметр от чужого (см. watch ниже). */
const ROUTE_NAME = 'tasks-task'

const { t } = useI18n()
const route = useRoute()
const router = useRouter()
const store = useTaskDetailStore()

const code = computed(() => String(route.params.code ?? ''))
const task = computed(() => store.task)
const deleted = computed(() => Boolean(task.value?.deleted_at))

// Страница живёт в KeepAlive: `onMounted` отрабатывает первый показ, `onActivated` — каждое
// возвращение (задачу могли поправить из списка, пока страница лежала в кеше).
onMounted(() => void store.load(code.value))
onActivated(() => void store.load(code.value))

// Уехавшая страница уносит свой `watch` с собой не сразу, и параметр чужого маршрута прилетел бы
// сюда же: сверяемся с именем маршрута, а не только с кодом.
watch(
  () => route.params.code,
  (value) => {
    if (route.name !== ROUTE_NAME || !value) return
    void store.load(String(value))
  },
)

// ── Черновик полей ────────────────────────────────────────────────────────────
// Правка ведёт СВОЮ копию значений (`draft`), а рядом хранит, от какой версии карточки она взята
// (`base`). Три версии поля — моя, `base` и свежая из базы — нужны потому, что карточку меняют и
// без этой страницы: агент через MCP, другая вкладка. Каждый раз, когда карточка в сторе
// меняется (перечитка по ленте изменений, «Обновить», возвращение на страницу, ответ на своё
// сохранение), она СЛИВАЕТСЯ с черновиком (`merge`):
//
// - в базе поле не менялось → черновик как есть (что бы человек в нём ни набрал);
// - менялось, а человек его не трогал → черновик берёт значение из базы;
// - менялось, и человек его правил → побеждает база: агент уже записал своё и на него
//   рассчитывает. Набранное человеком не пропадает молча — оно показано в окне конфликта, чтобы
//   его можно было скопировать (`conflicts`).
//
// Сохраняется только то, чем черновик отличается от `base` (`pending`), и только эти поля
// уезжают на бэк (`PATCH`). Раньше «что поменялось» считалось от свежей карточки: после её
// перечитки несохранённый черновик отличался от неё во ВСЕХ полях, которые менял агент, и первое
// же сохранение откатывало его правки.
const draft = reactive({
  title: '',
  description: '',
  context: '',
  constraints: '',
  criteria: '',
  body: '',
  type: TASK_TYPES[0] as string,
  priority: 'normal',
  groupCode: null as string | null,
  deadlineAt: null as Date | null,
})

/** Поля черновика, которые сливаются и сохраняются. Срок сравнивается по ДНЮ (`deadline`). */
const FIELDS = [
  'title', 'description', 'context', 'constraints', 'criteria', 'body',
  'type', 'priority', 'groupCode', 'deadline',
] as const
type Field = (typeof FIELDS)[number]
type Snapshot = Record<Field, string | null>

/**
 * Поля карточки в той форме, в какой их сравнивают с черновиком. Срок — днём, а не моментом: в
 * базе у него есть время суток, а поле выбирает только день.
 */
function snapshotOf(row: TaskDetail | null): Snapshot {
  return {
    title: row?.title ?? '',
    description: row?.description ?? '',
    context: row?.context ?? '',
    constraints: row?.constraints ?? '',
    criteria: row?.criteria ?? '',
    body: row?.body ?? '',
    type: row?.type ?? TASK_TYPES[0],
    priority: row?.priority ?? 'normal',
    groupCode: row?.group_code ?? null,
    deadline: deadlineDay(row?.deadline_at ?? null),
  }
}

/** Значение поля черновика в той же форме. Заголовок и цель уезжают обрезанными — так и сравниваем. */
function draftValue(field: Field): string | null {
  switch (field) {
    case 'deadline': return formatDay(draft.deadlineAt)
    case 'title': return draft.title.trim()
    case 'description': return draft.description.trim()
    default: return draft[field]
  }
}

/** Положить в черновик значение поля из карточки. */
function takeFromRow(field: Field, row: TaskDetail | null): void {
  switch (field) {
    case 'deadline': draft.deadlineAt = parseDay(row?.deadline_at ?? null); return
    case 'groupCode': draft.groupCode = row?.group_code ?? null; return
    default: draft[field] = (snapshotOf(row)[field] ?? '') as string
  }
}

/** Версия карточки, от которой взят черновик. После своего сохранения — то, что отправили. */
let base: Snapshot = snapshotOf(null)

watch(task, (next, prev) => {
  if (!next || !prev || next.code !== prev.code) {
    fillDraft()
    if (next) void loadGroups()
    return
  }
  merge(next)
})

/** Черновик = карточка как она в базе. Зовётся при смене задачи. */
function fillDraft(): void {
  const row = task.value
  for (const field of FIELDS) takeFromRow(field, row)
  base = snapshotOf(row)
  conflicts.value = []
}

// ── Конфликт: поле, которое человек правит, изменили в базе ─────────────────────
interface FieldConflict {
  field: Field
  /** Что человек успел набрать — показывается в окне, чтобы скопировать нужное. */
  mine: string
}

const conflicts = ref<FieldConflict[]>([])
const conflictOpen = computed({
  get: () => conflicts.value.length > 0,
  set: (open: boolean) => { if (!open) conflicts.value = [] },
})

/** Подпись поля в окне конфликта — та же, что у поля на странице. */
const FIELD_LABELS: Record<Field, string> = {
  title: 'tasks.task.form.name',
  description: 'tasks.task.detail.description',
  context: 'tasks.task.detail.context',
  constraints: 'tasks.task.detail.constraints',
  criteria: 'tasks.task.detail.criteria',
  body: 'tasks.task.detail.body',
  type: 'tasks.task.detail.type',
  priority: 'tasks.task.detail.priority',
  groupCode: 'tasks.task.detail.group',
  deadline: 'tasks.task.form.deadline_at',
}

/** Набранное человеком — словами, а не кодами: тип, приоритет и группа показаны названиями. */
function conflictText(conflict: FieldConflict): string {
  switch (conflict.field) {
    case 'type': return t(`tasks.task.type.${conflict.mine}`)
    case 'priority': return t(`tasks.task.priority.${conflict.mine}`)
    case 'groupCode':
      return groups.value.find((group) => group.code === conflict.mine)?.title ?? conflict.mine
    default: return conflict.mine
  }
}

const conflictItems = computed(() =>
  conflicts.value.map((conflict) => ({
    label: t(FIELD_LABELS[conflict.field]),
    text: conflictText(conflict),
  })),
)

// Карточка могла уже лежать в сторе к моменту первого монтирования (страницу пересоздали, а стор
// жив): `watch` выше срабатывает только на СМЕНУ карточки, и без этого черновик остался бы пустым.
if (task.value) fillDraft()

/** Слить свежую карточку с черновиком — правила в шапке раздела «Черновик полей». */
function merge(row: TaskDetail): void {
  const remote = snapshotOf(row)
  const found: FieldConflict[] = []
  for (const field of FIELDS) {
    if (remote[field] === base[field]) continue
    const mine = draftValue(field)
    if (mine === base[field] || mine === remote[field]) {
      takeFromRow(field, row)
      continue
    }
    found.push({ field, mine: mine ?? '' })
    takeFromRow(field, row)
  }
  base = remote
  // Окно показывает все столкновения, накопленные до его закрытия, — новое не стирает прежнее.
  if (found.length) conflicts.value = [...conflicts.value, ...found]
}

/**
 * Что показывать при этом типе задачи.
 *
 * Переключение типа НИЧЕГО НЕ СТИРАЕТ: скрытые поля остаются в базе и возвращаются, если тип
 * вернуть назад. Иначе «посмотреть, как выглядит простая» стоило бы человеку написанной
 * постановки — а отменить это нечем, у страницы нет отмены.
 */
const layout = computed(() => typeLayout(draft.type))

/**
 * Чем черновик разошёлся с `base` — и только это уедет на бэк. Прошёл по полям, ничего не
 * изменив, — запроса нет вовсе.
 *
 * Срок сравнивается по ДНЮ: в базе у него есть время суток, и, приведи мы обе стороны к
 * «23:59:59», правка соседнего поля молча переносила бы чужой срок на конец дня.
 */
function pending(): { body: Partial<TaskUpdateBody>; fields: Field[] } {
  const body: Partial<TaskUpdateBody> = {}
  const fields: Field[] = []
  if (!task.value) return { body, fields }
  for (const field of FIELDS) {
    const value = draftValue(field)
    if (value === base[field]) continue
    // Пустой заголовок не сохраняется: без него строка неразличима в списке — поле остаётся
    // пустым на экране, а в базе продолжает жить прежнее имя.
    if (field === 'title' && !value) continue
    fields.push(field)
    if (field === 'groupCode') body.group_code = draft.groupCode
    else if (field === 'deadline') body.deadline_at = formatDeadline(draft.deadlineAt)
    else body[field] = value ?? ''
  }
  return { body, fields }
}

let timer: ReturnType<typeof setTimeout> | null = null

function stopTimer(): void {
  if (timer === null) return
  clearTimeout(timer)
  timer = null
}

/** Последнее сохранение в полёте: перечитка по ленте ждёт его, чтобы не обогнать свой же ответ. */
let saving: Promise<unknown> = Promise.resolve()

/**
 * Отправить накопленное. Зовётся по уходу из поля, по смене выбора и перед уходом со страницы.
 *
 * `base` отправленных полей сдвигается на отправленное ДО ответа: пока запрос в полёте, человек
 * может печатать дальше, и ответ со «своим же» значением не должен выглядеть чужой правкой.
 * Отказ возвращает прежнюю `base` — поле снова числится несохранённым и уедет следующим разом.
 */
async function commit(): Promise<void> {
  stopTimer()
  if (deleted.value) return

  const { body, fields } = pending()
  if (fields.length === 0) return

  const before = { ...base }
  for (const field of fields) base[field] = draftValue(field)
  const request = store.patch(body)
  saving = request
  if (!(await request)) {
    for (const field of fields) base[field] = before[field]
  }
}

/** Набор продолжается: отправляем не на каждую букву, а когда человек остановился. */
function schedule(): void {
  stopTimer()
  timer = setTimeout(() => { timer = null; void commit() }, TYPING_PAUSE)
}

/** Выбор и даты едут сразу: паузе тут нечего ждать — значение уже окончательное. */
function pick<K extends keyof typeof draft>(key: K, value: (typeof draft)[K]): void {
  draft[key] = value
  void commit()
}

onBeforeUnmount(stopTimer)
onBeforeRouteLeave(() => { void commit() })

// ── Группы ────────────────────────────────────────────────────────────────────
// Список групп зависит от пространства задачи, а оно известно только из самой карточки.
const groups = ref<GroupRow[]>([])

async function loadGroups() {
  const workspace = task.value?.workspace_code
  if (!workspace) {
    groups.value = []
    return
  }
  try {
    // `report: false` — справочник едет фоном под полем; тост о нём человек не связал бы с тем,
    // что делает. Пустой список групп честнее: задача проживёт и без группы.
    groups.value = await listGroups({ workspace }, { report: false })
  } catch {
    groups.value = []
  }
}

// ── Справочники ───────────────────────────────────────────────────────────────

// Справочник статусов собирает сам `TaskStatusSelect`: порядок и значки живут в `labels.ts`, и
// собирать их здесь заново значило бы разойтись на первой же правке справочника.
const typeItems = computed(() =>
  TASK_TYPES.map((value) => ({ value, title: t(`tasks.task.type.${value}`) })),
)
// Вид группы едет в пункт вместе с именем: значок рисуется в списке и в самом поле, и брать
// его потом по коду значило бы искать группу второй раз на каждую отрисовку.
const groupItems = computed(() =>
  groups.value.map((group) => ({
    value: group.code,
    title: group.title,
    icon: group.icon,
    color: group.color,
  })),
)

// Смену статуса ведёт стор: поле только сообщает выбранное. Через `computed` с сеттером, а не
// через локальную копию, — иначе на отказе поле осталось бы показывать то, чего в базе нет.
const status = computed({
  get: () => task.value?.status ?? '',
  set: (value: string) => { void store.changeStatus(value) },
})

// ── Отметки времени ───────────────────────────────────────────────────────────
// Только то, что задача проставляет себе САМА: править эти значения нечем, и место им под
// полями, а не между ними. Пустые не показываются — строка «Завершено: —» не отвечает ни на один
// вопрос, зато отодвигает те, что отвечают.
const marks = computed(() => {
  const row = task.value
  if (!row) return []
  return [
    { key: 'started_at', label: t('tasks.task.detail.started_at'), value: row.started_at ? fmtDateTime(row.started_at) : '' },
    { key: 'completed_at', label: t('tasks.task.detail.completed_at'), value: row.completed_at ? fmtDateTime(row.completed_at) : '' },
    { key: 'canceled_at', label: t('tasks.task.detail.canceled_at'), value: row.canceled_at ? fmtDateTime(row.canceled_at) : '' },
    { key: 'created_by', label: t('tasks.task.detail.created_by'), value: t(`tasks.task.actor.${row.created_by}`) },
    { key: 'updated_at', label: t('tasks.task.detail.updated_at'), value: updatedAt.value },
  ].filter((mark) => mark.value)
})

// Точная дата отвечает «когда», относительная — «давно ли»; поодиночке каждая заставляет
// додумывать вторую.
const updatedAt = computed(() => {
  const value = task.value?.updated_at
  if (!value) return ''
  const relative = fmtRelative(value)
  return relative ? `${fmtDateTime(value)} (${relative})` : fmtDateTime(value)
})

// ── Длинные тексты ────────────────────────────────────────────────────────────
// Правка идёт свёрстанной: поле — тот же документ, что и на чтении, одной типографикой, и
// переключать нечего — ни «предпросмотр ↔ правка», ни «редактор ↔ исходник». Исходник убран
// решением постановщика: поле всегда в редакторе.
//
// ⚠️ Цена решения: редактор переносит не всё (`UNSUPPORTED` в мосте) — картинку, сноску, сырой
// HTML и блок внутри пункта списка он выбросит, если такое поле ПРАВИТЬ. Пока поле не тронуто,
// оно не уходит на бэк вовсе (см. `pending`), и написанное агентом цело.

/** Этап или запись журнала изменились — перечитываем задачу: списки едут внутри её ответа. */
function reloadTask(): void {
  void store.load(code.value)
}

/**
 * Кнопка «Обновить»: перечитать всё, что связано с задачей, — карточку (этапы, журнал, родитель и
 * дети едут в её ответе), ветку подзадач и справочник групп.
 *
 * Сначала уезжает набранное, потом перечитка; свежая карточка сливается с черновиком сама
 * (`merge`), так что поля показывают то, что в базе сейчас.
 */
const refreshing = ref(false)

async function refresh(): Promise<void> {
  refreshing.value = true
  try {
    await commit()
    await Promise.all([store.load(code.value), subtasks.value?.reload(), loadGroups()])
  } finally {
    refreshing.value = false
  }
}

// ── Живое обновление ──────────────────────────────────────────────────────────
// Страница подписана на ленту изменений (`useChangeSubscription`) и перечитывает задачу сама,
// когда её меняет кто-то другой: агент через MCP, другая вкладка. Своё эхо сюда не доходит.
// Перечитка ждёт своё сохранение в полёте — иначе её ответ мог бы обогнать ответ на него.

/** Изменение касается этой страницы? Коды — в той же форме, что в карточке (`TASK@…`). */
function concernsThisTask(change: Change): boolean {
  const row = task.value
  if (!row) return false
  // Массовая операция без названных кодов — не знаем, что задела, значит, могла и нас.
  if (change.ids.length === 0) return true
  const touches = (codes: (string | null | undefined)[]) =>
    codes.some((one) => one && (change.ids.includes(one) || change.refs.includes(one)))
  switch (change.entity) {
    case 'tasks.task':
      return [row.code, row.parent_code, ...row.children.map((child) => child.code)]
        .some((one) => one && change.ids.includes(one))
    case 'tasks.link':
    case 'tasks.stage':
    case 'tasks.note':
      return touches([row.code])
    case 'tasks.group':
      return touches([row.group_code, row.workspace_code])
    default:
      return false
  }
}

async function reloadLive(): Promise<void> {
  await saving
  await store.load(code.value)
}

useChangeSubscription({
  entities: ['tasks.task', 'tasks.link', 'tasks.stage', 'tasks.note', 'tasks.group'],
  match: concernsThisTask,
  onChange: (changes) => {
    if (changes.some((change) => change.entity !== 'tasks.group')) void reloadLive()
    if (changes.some((change) => change.entity === 'tasks.group')) void loadGroups()
  },
  onResync: () => {
    void reloadLive()
    void loadGroups()
  },
})

// ── Переходы и действия ───────────────────────────────────────────────────────

const purgeOpen = ref(false)
const formOpen = ref(false)
const parent = ref<TaskDetail | TaskListRow | null>(null)
// Правится из этой страницы только подзадача — строкой ветки; сама задача правится на месте.
const editing = ref<TaskListRow | null>(null)
const subtasks = ref<InstanceType<typeof TaskSubtasksPanel> | null>(null)

/** Путь соседней задачи: переход между задачами — обычная смена адреса, с записью в историю. */
function taskPath(target: string): string {
  return `/tasks/task/${encodeURIComponent(target)}`
}

/** Уход к соседней задаче — тоже уход: набранное дописывается раньше, чем сменится карточка. */
function goTask(target: string) {
  void commit()
  void router.push(taskPath(target))
}

/** Подзадача — открытой задачи или, из меню строки ветки, одной из её подзадач. */
function addChild(under?: TaskListRow) {
  editing.value = null
  parent.value = under ?? task.value
  formOpen.value = true
}

function editChild(child: TaskListRow) {
  editing.value = child
  parent.value = null
  formOpen.value = true
}

/**
 * Заведённая подзадача открывается сразу — её ради этого и заводили. Правленная из ветки остаётся
 * на месте: человек правил её строку, а не уходил к ней, — перечитывается ветка. Если сохранение
 * было правкой самой задачи, перечитываем её на месте.
 */
function onSaved(saved: string) {
  if (editing.value) {
    void subtasks.value?.reload()
    return
  }
  if (saved !== code.value) {
    void router.push(taskPath(saved))
    return
  }
  void store.load(code.value)
}

async function remove() {
  await store.remove()
}

async function restore() {
  await store.restore()
}

/** Снесённой задачи больше нет: оставаться на её адресе нельзя, и назад по истории тоже некуда. */
async function purge() {
  if (await store.purge()) {
    purgeOpen.value = false
    void router.replace('/tasks/list')
  }
}
</script>

<template>
  <PageLayout>
    <PageHeader :title="task?.title || t('tasks.task.detail.title')" back-to="/tasks/list">
      <!-- Название стоит там же, где у страницы стоит заголовок, и правится прямо в нём: это
           самое частое изменение задачи, и отдельного поля под него в теле страницы быть не должно. -->
      <template v-if="task" #title>
        <VTextField
          :model-value="draft.title"
          :placeholder="t('tasks.task.form.name')"
          :aria-label="t('tasks.task.form.name')"
          :maxlength="TASK_TITLE_MAX"
          :disabled="deleted"
          :error="!draft.title.trim()"
          variant="plain"
          hide-details
          class="task-page__title quiet-field"
          @update:model-value="(value) => { draft.title = value; schedule() }"
          @blur="commit"
        />
      </template>

      <template v-if="task" #description>
        <CopyChip :text="task.code" :hint="t('common.action.copy_code')" class="task-page__code" />
      </template>

      <template v-if="task" #actions>
        <VBtn variant="text" :disabled="refreshing" @click="refresh">
          <template #prepend><IconRefresh :size="16" :class="{ 'icon-spin': refreshing }" /></template>
          {{ t('common.action.refresh') }}
        </VBtn>
        <VBtn variant="text" :disabled="deleted" @click="addChild()">
          <template #prepend><IconPlus :size="16" /></template>
          {{ t('tasks.task.card.add_child') }}
        </VBtn>

        <!-- Редкое — в меню: снос необратим, и место ему рядом с удалением, а не в одном ряду с
             заведением подзадачи. -->
        <VMenu location="bottom end" :offset="4">
          <template #activator="{ props: menu }">
            <VBtn v-bind="menu" icon variant="text" :title="t('tasks.task.card.actions')">
              <IconDotsVertical :size="18" />
            </VBtn>
          </template>
          <VList density="compact">
            <VListItem v-if="!deleted" :prepend-icon="IconTrash" :disabled="store.busy" @click="remove">
              <VListItemTitle>{{ t('tasks.task.card.delete') }}</VListItemTitle>
            </VListItem>
            <VListItem v-else :prepend-icon="IconArchiveOff" :disabled="store.busy" @click="restore">
              <VListItemTitle>{{ t('tasks.task.card.restore') }}</VListItemTitle>
            </VListItem>
            <VListItem :prepend-icon="IconFlame" class="task-menu-danger" @click="purgeOpen = true">
              <VListItemTitle>{{ t('tasks.task.card.purge') }}</VListItemTitle>
            </VListItem>
          </VList>
        </VMenu>
      </template>
    </PageHeader>

    <SectionError v-if="store.error" :error="store.error" />

    <div v-else-if="store.loading && !task" class="task-page__loading">
      <VProgressCircular indeterminate size="28" width="3" />
    </div>

    <div v-else-if="task" class="task-page">
      <!-- Состояние корзины сказано полосой во всю ширину, а не шильдиком: пока задача удалена,
           ей нельзя ни править поля, ни менять статус, и человек должен узнать об этом раньше,
           чем упрётся в запертое поле. -->
      <VAlert v-if="deleted" type="warning" variant="tonal" density="compact">
        {{ t('tasks.task.detail.deleted_note') }}
        <template #append>
          <VBtn size="small" variant="text" :loading="store.busy" @click="restore">
            {{ t('tasks.task.card.restore') }}
          </VBtn>
        </template>
      </VAlert>

      <div class="task-page__grid">
        <div class="task-page__main">
          <!-- Где задача стоит: ссылка на родителя. У корневой её нет — и подниматься некуда. -->
          <button v-if="task.parent" type="button" class="task-page__parent" @click="goTask(task.parent.code)">
            <IconArrowUp :size="14" :stroke-width="1.6" />
            {{ task.parent.title }}
          </button>

          <!-- У каждой карточки текста — заголовок и под ним подзаголовок: ЧТО писать в этом поле.
               Подсказка стоит в шапке, а не в пустом поле, потому что нужна не только пустому:
               заполненная карточка без неё не говорит, чего от неё ждали. Пустое поле показывает
               свою подсказку редактора — как добавить блок командой через «/». -->
          <VCard variant="outlined" rounded="lg" class="task-page__card">
            <SectionHeader
              :title="t('tasks.task.detail.description')"
              :description="t('tasks.task.detail.hint.description')"
            />
            <!-- Цель — одна-две фразы, поэтому простой режим: абзац, жирный, курсив. Заголовку
                 или таблице в цели взяться неоткуда, и схема их просто не знает. -->
            <MarkdownEditor
              :model-value="draft.description"
              :aria-label="t('tasks.task.detail.description')"
              :max-length="TASK_DESCRIPTION_MAX"
              :readonly="deleted"
              mode="simple"
              variant="plain"
              min-height="0"
              @update:model-value="(value) => { draft.description = value; schedule() }"
              @blur="commit"
            />
          </VCard>

          <!-- Контекст есть у любой задачи, даже простой: это «что надо знать, чтобы взяться», и
               без него простая карточка превращается в одну строку заголовка. -->
          <VCard variant="outlined" rounded="lg" class="task-page__card">
            <SectionHeader
              :title="t('tasks.task.detail.context')"
              :description="t('tasks.task.detail.hint.context')"
            />
            <MarkdownEditor
              :model-value="draft.context"
              :aria-label="t('tasks.task.detail.context')"
              :max-length="TASK_CONTEXT_MAX"
              :readonly="deleted"
              :features="TASK_DOCUMENT_FEATURES"
              variant="plain"
              min-height="0"
              @update:model-value="(value) => { draft.context = value; schedule() }"
              @blur="commit"
            />
          </VCard>

          <!-- Границы и требования к сдаче — постановка стандартной задачи. У простой их нет:
               там нечего сдавать по критериям, и пустые поля только занимали бы экран. -->
          <VCard v-if="layout.brief" variant="outlined" rounded="lg" class="task-page__card">
            <SectionHeader
              :title="t('tasks.task.detail.constraints')"
              :description="t('tasks.task.detail.hint.constraints')"
            />
            <MarkdownEditor
              :model-value="draft.constraints"
              :aria-label="t('tasks.task.detail.constraints')"
              :max-length="TASK_CONSTRAINTS_MAX"
              :readonly="deleted"
              :features="TASK_BRIEF_FEATURES"
              variant="plain"
              min-height="0"
              @update:model-value="(value) => { draft.constraints = value; schedule() }"
              @blur="commit"
            />
          </VCard>

          <VCard v-if="layout.brief" variant="outlined" rounded="lg" class="task-page__card">
            <SectionHeader
              :title="t('tasks.task.detail.criteria')"
              :description="t('tasks.task.detail.hint.criteria')"
            />
            <MarkdownEditor
              :model-value="draft.criteria"
              :aria-label="t('tasks.task.detail.criteria')"
              :max-length="TASK_CRITERIA_MAX"
              :readonly="deleted"
              :features="TASK_BRIEF_FEATURES"
              variant="plain"
              min-height="0"
              @update:model-value="(value) => { draft.criteria = value; schedule() }"
              @blur="commit"
            />
          </VCard>

          <VCard v-if="layout.plan" variant="outlined" rounded="lg" class="task-page__card">
            <SectionHeader
              :title="t('tasks.task.detail.body')"
              :description="t('tasks.task.detail.hint.body')"
            />
            <MarkdownEditor
              :model-value="draft.body"
              :aria-label="t('tasks.task.form.body')"
              :max-length="BODY_MAX"
              :readonly="deleted"
              :features="TASK_DOCUMENT_FEATURES"
              variant="plain"
              min-height="0"
              @update:model-value="(value) => { draft.body = value; schedule() }"
              @blur="commit"
            />
          </VCard>

          <!-- Этапы и журнал — работа по задаче, и место им сразу под планом: план обещает, этапы
               показывают ход, журнал держит то, что всплыло по дороге.
               Этапы — только у расширенной, и это единственное, чем она отличается от
               стандартной: у той план живёт прозой выше, а разбивать его на шаги с отдельными
               доказательствами имеет смысл только у работы длиннее одного захода. -->
          <section v-if="layout.stages">
            <SectionHeader :title="t('tasks.stage.section')" :count="task.stages.length" />
            <TaskStages
              :task-code="task.code"
              :stages="task.stages"
              :disabled="deleted"
              @changed="reloadTask"
            />
          </section>

          <section v-if="layout.plan">
            <SectionHeader :title="t('tasks.note.section')" :count="task.notes.length" />
            <TaskJournal
              :task-code="task.code"
              :notes="task.notes"
              :disabled="deleted"
              @changed="reloadTask"
            />
          </section>

          <section>
            <SectionHeader :title="t('tasks.task.detail.children')" :count="task.children.length">
              <template #right>
                <VBtn variant="text" size="small" :disabled="deleted" @click="addChild()">
                  <template #prepend><IconPlus :size="16" /></template>
                  {{ t('tasks.task.card.add_child') }}
                </VBtn>
              </template>
            </SectionHeader>

            <!-- Ветка под задачей — тем же видом, что в общем списке, со своим поиском и
                 переключателями; каждая строка открывает СВОЮ страницу. -->
            <TaskSubtasksPanel
              ref="subtasks"
              :task-code="task.code"
              :workspace="task.workspace_code"
              :deleted="deleted"
              @open="goTask"
              @edit="editChild"
              @add-child="addChild"
            />
          </section>
        </div>

        <!-- Карточка сама себе `aside`: отдельная обёртка вокруг неё добавила бы уровень, на
             котором нечему жить — колонка полей и есть эта карточка. -->
        <VCard tag="aside" variant="outlined" rounded="lg" class="task-page__side">
          <!-- Строка состояния молчит в покое: кнопки сохранения нет, поэтому про ошибку и про
               идущую запись сказать обязательно, а про то, что всё сохранено, — нет. Пустая
               строка в покое не занимала бы места, но занимала бы место в голове. -->
          <p
            v-if="store.saveError || store.saving"
            class="task-page__save"
            :class="{ 'task-page__save--error': store.saveError }"
          >
            {{ store.saveError || t('tasks.task.detail.saving') }}
          </p>

          <!-- Группа необязательна: задача без неё попадает в секцию «Без группы», а не теряется.
               Групп в пространстве бывает много, и узнают их по виду — иконке в цвете группы,
               тому же, что в списке задач. Поиск прикреплён сверху меню и поле не меняет.
               `:chips="false"` обязателен: с чипами Vuetify рисует `#chip` и молча игнорирует
               `#selection`, то есть выбранная группа осталась бы без значка. -->
          <VSelectSearch
            :model-value="draft.groupCode"
            :items="groupItems"
            :label="t('tasks.task.detail.group')"
            :search-placeholder="t('tasks.task.detail.group_search')"
            :no-data-text="t('tasks.task.detail.group_empty')"
            :disabled="deleted"
            :chips="false"
            variant="outlined"
            density="compact"
            clearable
            hide-details
            @update:model-value="(value) => pick('groupCode', (value ?? null) as string | null)"
          >
            <template #item="{ props: itemProps, item }">
              <VListItem v-bind="itemProps">
                <template #prepend>
                  <IconSwatch :icon="item.icon" :color="item.color" :width="20" />
                </template>
              </VListItem>
            </template>

            <template #selection="{ item }">
              <span class="task-page__group-value">
                <IconSwatch :icon="item.icon" :color="item.color" :width="20" />
                {{ item.title }}
              </span>
            </template>
          </VSelectSearch>

          <!-- Статус ходят по соседям — из плана в работу, из работы на проверку, — поэтому
               поле со ступенями, как у приоритета, и со значком: тем же, что стоит в строке
               списка задач. -->
          <TaskStatusSelect
            v-model="status"
            :label="t('tasks.task.detail.status')"
            :disabled="deleted || store.busy"
            :loading="store.busy"
            variant="outlined"
            density="compact"
            hide-details
          />

          <TaskPrioritySelect
            :model-value="draft.priority"
            :label="t('tasks.task.detail.priority')"
            :disabled="deleted"
            variant="outlined"
            density="compact"
            hide-details
            @update:model-value="(value) => pick('priority', value as string)"
          />

          <!-- Единственная назначаемая дата: до какого числа успеть. Выбранный день уезжает
               последней секундой суток (`formatDeadline`), иначе срок «на сегодня» был бы
               просрочен с самого утра. -->
          <!-- Значок календаря переезжает ВНУТРЬ поля: снаружи (`prepend-icon`, умолчание
               VDateInput) он стоит отдельной коробкой перед рамкой, и поле съезжает вправо на
               32px — в колонке, где все остальные поля начинаются по одной линии, это видно. -->
          <VDateInput
            :model-value="draft.deadlineAt"
            :label="t('tasks.task.detail.deadline_at')"
            :disabled="deleted"
            prepend-icon=""
            :prepend-inner-icon="IconCalendarEvent"
            variant="outlined"
            density="compact"
            clearable
            hide-details
            @update:model-value="(value) => pick('deadlineAt', (value ?? null) as Date | null)"
          />

          <!-- Тип выбирается кнопками: все три значения видны сразу, без раскрытия списка.
               Вид взят у дизайн-системы — `outlined` + `divided`, как умолчание проекта для
               `VBtnToggle` (plugins/vuetify.ts) и как показано в витрине. Прежний `tonal`
               заливал выбранное сплошным цветом, и ряд читался тяжёлой полосой.
               Стоит последним из полей: тип ставят один раз при заведении, а меняют реже всего
               остального в этой колонке. -->
          <div class="task-page__field">
            <span class="task-page__label">{{ t('tasks.task.detail.type') }}</span>
            <VBtnToggle
              :model-value="draft.type"
              mandatory
              divided
              variant="outlined"
              density="compact"
              :disabled="deleted"
              class="task-page__toggle"
              @update:model-value="(value) => pick('type', value as string)"
            >
              <VBtn v-for="item in typeItems" :key="item.value" :value="item.value">
                {{ item.title }}
              </VBtn>
            </VBtnToggle>
            <span class="task-page__hint">{{ t('tasks.task.detail.type_hint') }}</span>
          </div>

          <dl v-if="marks.length" class="task-page__marks">
            <div v-for="mark in marks" :key="mark.key" class="task-page__mark">
              <dt class="task-page__mark-label">{{ mark.label }}</dt>
              <dd class="task-page__mark-value">{{ mark.value }}</dd>
            </div>
          </dl>
        </VCard>
      </div>
    </div>

    <!-- Поле, которое человек правил, тем временем изменили в базе: на странице уже версия из
         базы, а набранное — здесь, чтобы его можно было скопировать. -->
    <TaskFieldConflictDialog v-model="conflictOpen" :items="conflictItems" />

    <TaskFormDialog
      v-model="formOpen"
      :workspace="task?.workspace_code ?? ''"
      :task="editing"
      :parent="parent"
      @saved="onSaved"
    />

    <ConfirmDialog
      v-model="purgeOpen"
      :title="t('tasks.task.purge.title')"
      :text="task?.has_children ? t('tasks.task.purge.with_children') : t('tasks.task.purge.text')"
      :confirm-label="t('tasks.task.card.purge')"
      :loading="store.busy"
      @confirm="purge"
    />
  </PageLayout>
</template>

<style scoped>
.task-page__loading {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 200px;
}

.task-page {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

/* Колонка полей не тянется и не жмётся: её ширину задают поля внутри, а всё остальное место
   достаётся прозе. Ниже 900px колонки встают друг под друга — половинка экрана под текст задачи
   уже не колонка чтения. */
/* 312px = 280px полей + падинг карточки с двух сторон: колонка обзавелась рамкой, а поля внутри
   обязаны остаться той же ширины, иначе ряд переключателя типа сожмётся ещё на 32px. */
.task-page__grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 312px;
  gap: 28px;
  align-items: start;
}

@media (max-width: 900px) {
  .task-page__grid { grid-template-columns: minmax(0, 1fr); gap: 20px; }
}

.task-page__main {
  display: flex;
  flex-direction: column;
  gap: 16px;
  min-width: 0;
}

/* Карточка получает только текстовая секция. Этапы, журнал и подзадачи остаются на полотне: у
   каждой их строки своя рамка, и карточка вокруг дала бы рамку в рамке.
   16px — между панелью фильтров (12px) и плиткой группы (18px): здесь пять карточек в колонке
   подряд, и каждый лишний пиксель отступа умножается на пять.
   Правило про рамку в рамке действует и ВНУТРИ карточки, поэтому поля прозы набраны тихими
   (`quiet-field`, как заголовок страницы): рамка у секции одна — сама карточка, а то, что поле
   можно править, показывают подложка под курсором и обводка под фокусом. */
.task-page__card {
  padding: 16px;
}

/* Колонка полей держится в виду, пока листают длинный текст: статус и срок нужны на любой его
   строке, а уехавшие вверх поля пришлось бы искать прокруткой обратно. Липнет она только в
   двухколоночной раскладке — в одноколоночной липкая полоса накрывала бы сам текст.
   Поля набраны самой плотной ступенью (28px), а расстояние между ними, наоборот, больше
   обычного: в колонке из шести полей подряд рост коробки только отнимает место, а различает
   поля пустота вокруг них. */
.task-page__side {
  display: flex;
  flex-direction: column;
  gap: 18px;
  min-width: 0;
  padding: 16px;
  position: sticky;
  top: 0;
}

@media (max-width: 900px) {
  .task-page__side { position: static; }
}

/* Поднятая метка набрана мельче своего значения: общее правило `.v-field .v-label` из main.scss
   прибивает ей 13px и лежит ВНЕ слоёв, поэтому собственный масштаб Vuetify (0.75em) до неё не
   доходит — метка выходит ростом со значением и в узкой колонке читается второй строкой поля, а
   не его именем. Сдвиг вверх — над линией рамки, на которую Vuetify сажает её серединой. */
.task-page__side :deep(.v-field .v-label.v-field-label--floating) {
  font-size: 11px;
  transform: translateY(calc(-50% - 2px));
}

/* Ссылка вверх набрана кнопкой, а не `RouterLink`: адресом заведует страница, и разметка не
   должна знать, как он собран. Выглядит она при этом ссылкой — это и есть переход. */
.task-page__parent {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  align-self: flex-start;
  max-width: 100%;
  padding: 0;
  border: none;
  background: none;
  font-size: 12px;
  color: var(--text-muted);
  cursor: pointer;
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
  transition: color 0.14s ease;
}

.task-page__parent:hover { color: var(--text); }

/* Поле без рамки: в покое это текст, под курсором — подложка, под фокусом — обводка акцентом.
   Отступы совпадают с этой подложкой, поэтому вход в правку не сдвигает ни буквы. */
.quiet-field :deep(.v-field) {
  padding-inline: 8px;
  border-radius: var(--radius-sm);
  transition: background-color 0.14s ease;
}

.quiet-field :deep(.v-field:hover) { background: var(--surface-hi); }

.quiet-field :deep(.v-field--focused) {
  background: var(--input-bg);
  box-shadow: inset 0 0 0 1px var(--accent);
}

/* Текстовая половина шапки ужимается по содержимому: обычному заголовку это ровно его длина, а
   полю — его собственная ширина, около 20 символов, в которые не влезает и половина имени задачи.
   Растягиваем её здесь, а не в общем `SectionHeader`: поле в заголовке пока только у задачи. */
:deep(.section-header__text) {
  flex: 1 1 auto;
}

/* Поле заголовка стоит НА МЕСТЕ заголовка страницы и обязано занимать ровно его строку: метрика
   взята у заголовка первого уровня, а вертикальные поля выведены из расчёта высоты обратным
   отступом — иначе шапка выросла бы на высоту поля и разъехалась с шапками остальных страниц. */
.task-page__title {
  width: 100%;
  margin-inline-start: -8px;
}

.task-page__title :deep(.v-field__input) {
  min-height: 28px;
  padding-block: 4px;
  margin-block: -4px;
  font-size: 22px;
  font-weight: 700;
  line-height: 28px;
}

/* Плашка кода: отрицательное поле слева выводит её собственную отбивку из строки — значок
   копирования стоит по левому краю заголовка над ним, а подложка под курсором выступает за край,
   как у кнопки. */
.task-page__code {
  margin-inline-start: -5px;
}

/* Строка состояния правки стоит над полями и молчит в покое — сообщением она становится только
   когда правка в полёте или не дошла. */
.task-page__save {
  margin: 0;
  min-height: 16px;
  font-size: 11px;
  color: var(--text-faint);
}

.task-page__save--error { color: var(--error); }

/* Подпись прижата к своему полю теснее, чем поля друг к другу, — иначе она читается как
   заголовок всего блока, а не как пояснение к полю. */
.task-page__field {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

/* Значок и имя группы в поле стоят тем же рядом, что и в пункте списка: выбранное значение —
   это тот же пункт, только показанный в поле. */
.task-page__group-value {
  display: inline-flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
}

/* У ряда кнопок нет поднятой метки, как у соседних полей, поэтому имя стоит строкой над ним. */
.task-page__label {
  font-size: 12px;
  color: var(--text-muted);
}

/* Подпись под типом: она объясняет поведение, а не называет поле, поэтому тише метки и стоит
   ПОД рядом, а не над ним. */
.task-page__hint {
  font-size: 11px;
  line-height: 1.4;
  color: var(--text-faint);
}

/* Размер у группы кнопок не наследуется детьми (docs/conventions/frontend.md), поэтому высота
   ставится руками — по соседним полям, а они здесь идут плотной ступенью. Подписи в 11 символов
   делят ширину колонки поровну, поэтому шрифт на ступень мельче кнопочного. */
.task-page__toggle { width: 100%; }

.task-page__toggle :deep(.v-btn) {
  flex: 1;
  min-width: 0;
  height: 28px;
  padding-inline: 6px;
  font-size: 12px;
  letter-spacing: 0;
  text-transform: none;
}

/* Отметки времени идут строками «метка / значение» под полями: их не правят, и место под
   колонкой полей у них общее. */
.task-page__marks {
  display: flex;
  flex-direction: column;
  gap: 10px;
  margin: 0;
  padding-top: 14px;
  border-top: 1px solid var(--border);
}

.task-page__mark { min-width: 0; }

.task-page__mark-label {
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--text-faint);
}

.task-page__mark-value {
  margin: 2px 0 0;
  font-size: 12px;
  color: var(--text);
}

.task-menu-danger :deep(.v-list-item-title) { color: var(--error); }
.task-menu-danger :deep(.v-list-item__prepend) { color: var(--error); }
</style>
