<script setup lang="ts">
// The whole task — a PAGE at `/tasks/task/TASK@…`, not a dialog over the list.
//
// Why a page. A task is not so much viewed as worked in: editing text, moving the status, creating
// and opening subtasks. A dialog had neither the room for that (prose and the classification
// column shared the modal's width) nor the permanence — it closed in passing. A page has its own
// URL, its own navigation history and the full screen width.
//
// EDITING HAPPENS RIGHT HERE. The task has no separate form: fields are edited in place and save
// themselves — text fields after a typing pause and on leaving the field, selects and dates right
// on change. There is no save button and no "cancel" either: the task's only state is what is in
// the database. Leaving the page flushes what was typed (`onBeforeRouteLeave`): navigating away
// must not cost the last sentence.
//
// Two columns, and the line between them is about meaning. On the left is what the person READS
// through — the description, the task text — and the links to neighbouring tasks: the parent above,
// subtasks below. On the right is what CLASSIFIES the task: status, type, priority, group, deadline
// and timestamps.
//
// The frame is the shared `PageLayout` with the shared page header; there is no navigation column
// like on the research detail pages: a task has no long document worth navigating by section with
// a table of contents, and the way up is the "back" button in the header.
import { computed, onActivated, onBeforeUnmount, onDeactivated, reactive, ref, watch } from 'vue'
import { onBeforeRouteLeave, useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import {
  IconArrowUp,
  IconCalendarEvent,
  IconDotsVertical,
  IconFlame,
  IconPlus,
  IconRefresh,
  IconRestore,
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
  TASK_CONSTRAINTS_MAX,
  TASK_CONTEXT_MAX,
  TASK_CRITERIA_MAX,
  TASK_DESCRIPTION_MAX,
  TASK_PLAN_MAX,
  TASK_PROGRESS_MAX,
  TASK_RESULT_MAX,
  TASK_TITLE_MAX,
  TASK_TYPES,
  typeLayout,
} from '../labels'
import { useTaskDetailStore } from '../stores/task-detail.store'

/** Silence in a field after which the typed text is sent to the backend. */
const TYPING_PAUSE = 700

/** Our own route name: it tells OUR parameter from another route's (see the watch below). */
const ROUTE_NAME = 'tasks-task'

const { t } = useI18n()
const route = useRoute()
const router = useRouter()
const store = useTaskDetailStore()

// Folded to upper case: a link or bookmark from before codes went upper case still carries the
// lower-case form, and the page compares this value with the codes the API returns.
const code = computed(() => String(route.params.code ?? '').toUpperCase())
const task = computed(() => store.task)
const deleted = computed(() => Boolean(task.value?.deleted_at))

// The page lives in KeepAlive, and `onActivated` fires both on first display and on every return
// (the task may have been edited from the list while the page sat in the cache). A second call
// from `onMounted` would send two identical requests in a row on first display.
let active = false

onActivated(() => {
  active = true
  void store.load(code.value)
  void loadGroups()
})

onDeactivated(() => { active = false })

// Navigating from task to task while the page is on screen: KeepAlive keeps a single instance, and
// there will be no activation. Returning from another page changes the parameter BEFORE
// activation — `onActivated` loads it, and here it would make a second identical request. A page
// that has been left does not drop its `watch` immediately, and another route's parameter would
// land here too: so the route name is checked as well.
watch(
  () => route.params.code,
  (value) => {
    if (!active || route.name !== ROUTE_NAME || !value) return
    void store.load(String(value))
  },
)

// ── Field draft ───────────────────────────────────────────────────────────────
// Editing keeps ITS OWN copy of the values (`draft`) and, next to it, which version of the card it
// was taken from (`base`). Three versions of a field — mine, `base` and the fresh one from the
// database — are needed because the card is also changed outside this page: the agent via MCP,
// another tab. Every time the card in the store changes (a re-read from the change feed,
// "Refresh", returning to the page, the response to our own save), it is MERGED into the draft
// (`merge`):
//
// - the field did not change in the database → the draft stays as is (whatever the person typed);
// - it changed and the person did not touch it → the draft takes the database value;
// - it changed and the person edited it → the database wins: the agent has already written its
//   value and relies on it. What the person typed is not lost silently — it is shown in the
//   conflict dialog so it can be copied (`conflicts`).
//
// Only what differs between the draft and `base` is saved (`pending`), and only those fields are
// sent to the backend (`PATCH`). "What changed" used to be computed against the fresh card: after
// a re-read, an unsaved draft differed from it in ALL the fields the agent had changed, and the
// very first save rolled back the agent's edits.
const draft = reactive({
  title: '',
  description: '',
  context: '',
  constraints: '',
  criteria: '',
  plan: '',
  progress: '',
  result: '',
  type: TASK_TYPES[0] as string,
  priority: 'normal',
  groupCode: null as string | null,
  deadlineAt: null as Date | null,
})

/** Draft fields that are merged and saved. The deadline is compared by DAY (`deadline`). */
const FIELDS = [
  'title', 'description', 'context', 'constraints', 'criteria', 'plan', 'progress', 'result',
  'type', 'priority', 'groupCode', 'deadline',
] as const
type Field = (typeof FIELDS)[number]
type Snapshot = Record<Field, string | null>

/**
 * Card fields in the form they are compared with the draft. The deadline as a day, not a moment:
 * in the database it has a time of day, while the field picks only the day.
 */
function snapshotOf(row: TaskDetail | null): Snapshot {
  return {
    title: row?.title ?? '',
    description: row?.description ?? '',
    context: row?.context ?? '',
    constraints: row?.constraints ?? '',
    criteria: row?.criteria ?? '',
    plan: row?.plan ?? '',
    progress: row?.progress ?? '',
    result: row?.result ?? '',
    type: row?.type ?? TASK_TYPES[0],
    priority: row?.priority ?? 'normal',
    groupCode: row?.group_code ?? null,
    deadline: deadlineDay(row?.deadline_at ?? null),
  }
}

/** A draft field's value in the same form. Title and goal are sent trimmed — so they are compared trimmed. */
function draftValue(field: Field): string | null {
  switch (field) {
    case 'deadline': return formatDay(draft.deadlineAt)
    case 'title': return draft.title.trim()
    case 'description': return draft.description.trim()
    default: return draft[field]
  }
}

/** Put a field's value from the card into the draft. */
function takeFromRow(field: Field, row: TaskDetail | null): void {
  switch (field) {
    case 'deadline': draft.deadlineAt = parseDay(row?.deadline_at ?? null); return
    case 'groupCode': draft.groupCode = row?.group_code ?? null; return
    default: draft[field] = (snapshotOf(row)[field] ?? '') as string
  }
}

/** The card version the draft was taken from. After our own save — what was sent. */
let base: Snapshot = snapshotOf(null)

watch(task, (next, prev) => {
  if (!next || !prev || next.code !== prev.code) {
    fillDraft()
    if (next) void loadGroups()
    return
  }
  merge(next)
})

/** Draft = the card as it is in the database. Called when the task changes. */
function fillDraft(): void {
  const row = task.value
  for (const field of FIELDS) takeFromRow(field, row)
  base = snapshotOf(row)
  conflicts.value = []
}

// ── Conflict: a field the person is editing was changed in the database ─────────
interface FieldConflict {
  field: Field
  /** What the person had typed — shown in the dialog so the needed part can be copied. */
  mine: string
}

const conflicts = ref<FieldConflict[]>([])
const conflictOpen = computed({
  get: () => conflicts.value.length > 0,
  set: (open: boolean) => { if (!open) conflicts.value = [] },
})

/** The field label in the conflict dialog — the same as the field's label on the page. */
const FIELD_LABELS: Record<Field, string> = {
  title: 'tasks.task.form.name',
  description: 'tasks.task.detail.description',
  context: 'tasks.task.detail.context',
  constraints: 'tasks.task.detail.constraints',
  criteria: 'tasks.task.detail.criteria',
  plan: 'tasks.task.detail.plan',
  progress: 'tasks.task.detail.progress',
  result: 'tasks.task.detail.result',
  type: 'tasks.task.detail.type',
  priority: 'tasks.task.detail.priority',
  groupCode: 'tasks.task.detail.group',
  deadline: 'tasks.task.form.deadline_at',
}

/** What the person typed — in words, not codes: type, priority and group are shown by name. */
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

// The card may already be in the store at first mount (the page was recreated, the store is
// alive): the `watch` above fires only on a CHANGE of card, and without this the draft would stay
// empty.
if (task.value) fillDraft()

/** Merge the fresh card into the draft — rules in the header of the "Field draft" section. */
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
  // The dialog shows all clashes accumulated until it is closed — a new one does not erase the old.
  if (found.length) conflicts.value = [...conflicts.value, ...found]
}

/**
 * What to show for this task type.
 *
 * Switching the type ERASES NOTHING: hidden fields stay in the database and come back if the type
 * is switched back. Otherwise "see what a simple one looks like" would cost the person their
 * written brief — and there is no way to undo that, the page has no undo.
 */
const layout = computed(() => typeLayout(draft.type))

/**
 * How the draft diverged from `base` — and only that goes to the backend. Tabbed through the
 * fields without changing anything — no request at all.
 *
 * The deadline is compared by DAY: in the database it has a time of day, and if we normalised both
 * sides to "23:59:59", editing a neighbouring field would silently move someone else's deadline to
 * the end of the day.
 */
function pending(): { body: Partial<TaskUpdateBody>; fields: Field[] } {
  const body: Partial<TaskUpdateBody> = {}
  const fields: Field[] = []
  if (!task.value) return { body, fields }
  for (const field of FIELDS) {
    const value = draftValue(field)
    if (value === base[field]) continue
    // An empty title is not saved: without it the row is indistinguishable in the list — the field
    // stays empty on screen, while the old name lives on in the database.
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

/** The last save in flight: a feed re-read waits for it so as not to overtake our own response. */
let saving: Promise<unknown> = Promise.resolve()

/**
 * Send what has accumulated. Called on leaving a field, on a select change and before leaving the
 * page.
 *
 * The `base` of the sent fields moves to the sent values BEFORE the response: while the request is
 * in flight the person may keep typing, and a response carrying "our own" value must not look like
 * a foreign edit. A refusal restores the previous `base` — the field counts as unsaved again and
 * goes out next time.
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

/** Typing continues: send not on every letter but when the person pauses. */
function schedule(): void {
  stopTimer()
  timer = setTimeout(() => { timer = null; void commit() }, TYPING_PAUSE)
}

/** Selects and dates go at once: there is nothing for a pause to wait for — the value is final. */
function pick<K extends keyof typeof draft>(key: K, value: (typeof draft)[K]): void {
  draft[key] = value
  void commit()
}

onBeforeUnmount(stopTimer)
onBeforeRouteLeave(() => { void commit() })
// ── Groups ────────────────────────────────────────────────────────────────────
// The group list depends on the task's workspace, which is known only from the card itself.
const groups = ref<GroupRow[]>([])

async function loadGroups() {
  const workspace = task.value?.workspace_code
  if (!workspace) {
    groups.value = []
    return
  }
  try {
    // `report: false` — the lookup loads in the background under the field; the person would not
    // connect a toast about it with what they are doing. An empty group list is more honest: the
    // task will do fine without a group.
    groups.value = await listGroups({ workspace }, { report: false })
  } catch {
    groups.value = []
  }
}

// ── Vocabularies ──────────────────────────────────────────────────────────────

// The status vocabulary is assembled by `TaskStatusSelect` itself: order and icons live in
// `labels.ts`, and assembling them anew here would diverge at the first edit of the vocabulary.
const typeItems = computed(() =>
  TASK_TYPES.map((value) => ({ value, title: t(`tasks.task.type.${value}`) })),
)
// The group's look travels into the item together with its name: the icon is drawn in the list
// and in the field itself, and fetching it by code later would mean looking the group up again on
// every render.
const groupItems = computed(() =>
  groups.value.map((group) => ({
    value: group.code,
    title: group.title,
    icon: group.icon,
    color: group.color,
  })),
)

// The store runs the status change: the field only reports the choice. Via a `computed` with a
// setter, not a local copy — otherwise on refusal the field would keep showing what is not in the
// database.
const status = computed({
  get: () => task.value?.status ?? '',
  set: (value: string) => { void store.changeStatus(value) },
})

// ── Timestamps ────────────────────────────────────────────────────────────────
// Only what the task stamps on ITSELF: these values cannot be edited, so they belong below the
// fields, not among them. Empty ones are not shown — a "Completed: —" line answers no question
// but pushes away those that do.
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

// The exact date answers "when", the relative one "how long ago"; each alone makes you work out
// the other.
const updatedAt = computed(() => {
  const value = task.value?.updated_at
  if (!value) return ''
  const relative = fmtRelative(value)
  return relative ? `${fmtDateTime(value)} (${relative})` : fmtDateTime(value)
})

// ── Long texts ────────────────────────────────────────────────────────────────
// Editing happens on the rendered text: the field is the same document as when reading, in one
// typography, and there is nothing to toggle — neither "preview ↔ edit" nor "editor ↔ source".
// The source view was removed by the task author's decision: the field is always in the editor.
//
// ⚠️ The cost of that decision: the editor does not carry everything over (`UNSUPPORTED` in the
// bridge) — an image, a footnote, raw HTML and a block inside a list item get dropped if such a
// field is EDITED. Until a field is touched it is not sent to the backend at all (see `pending`),
// and what the agent wrote stays intact.

/** A stage or journal entry changed — re-read the task: the lists come inside its response. */
function reloadTask(): void {
  void store.load(code.value)
}

/**
 * The "Refresh" button: re-read everything related to the task — the card (stages, journal,
 * parent and children come in its response), the subtask branch and the group lookup.
 *
 * What was typed goes out first, then the re-read; the fresh card merges into the draft by itself
 * (`merge`), so the fields show what is in the database now.
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

// ── Live updates ──────────────────────────────────────────────────────────────
// The page subscribes to the change feed (`useChangeSubscription`) and re-reads the task by itself
// when someone else changes it: the agent via MCP, another tab. Our own echo does not reach here.
// The re-read waits for our own save in flight — otherwise its response could overtake that one's.

/** Does the change concern this page? Codes are in the same form as in the card (`TASK@…`). */
function concernsThisTask(change: Change): boolean {
  const row = task.value
  if (!row) return false
  // A bulk operation with no named codes — we cannot tell what it touched, so it may have touched us.
  if (change.ids.length === 0) return true
  const touches = (codes: (string | null | undefined)[]) =>
    codes.some((one) => one && (change.ids.includes(one) || change.refs.includes(one)))
  switch (change.entity) {
    case 'tasks.task':
      return [row.code, row.parent_code, ...row.children.map((child) => child.code)]
        .some((one) => one && change.ids.includes(one))
    case 'tasks.link':
    case 'tasks.stage':
    case 'tasks.journal':
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
  entities: ['tasks.task', 'tasks.link', 'tasks.stage', 'tasks.journal', 'tasks.group'],
  match: concernsThisTask,
  onChange: (changes) => {
    if (changes.some((change) => change.entity !== 'tasks.group')) void reloadLive()
    if (changes.some((change) => change.entity === 'tasks.group')) void loadGroups()
  },
  onResync: () => {
    void reloadLive()
    void loadGroups()
  },
  reloadsOnReturn: true,
})

// ── Navigation and actions ────────────────────────────────────────────────────

const purgeOpen = ref(false)
const formOpen = ref(false)
const parent = ref<TaskDetail | TaskListRow | null>(null)
const subtasks = ref<InstanceType<typeof TaskSubtasksPanel> | null>(null)

/** Path of a neighbouring task: moving between tasks is an ordinary URL change, with a history entry. */
function taskPath(target: string): string {
  return `/tasks/task/${encodeURIComponent(target)}`
}

/** Going to a neighbouring task is leaving too: what was typed is flushed before the card changes. */
function goTask(target: string) {
  void commit()
  void router.push(taskPath(target))
}

/** A subtask — of the open task or, from a branch row's menu, of one of its subtasks. */
function addChild(under?: TaskListRow) {
  parent.value = under ?? task.value
  formOpen.value = true
}

/**
 * A newly created subtask opens right away — that is what it was created for. If the save was of
 * the task itself, it is re-read in place.
 */
function onSaved(saved: string) {
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

/** A purged task no longer exists: staying at its URL is impossible, and going back in history leads nowhere. */
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
      <!-- The title sits where the page's heading sits and is edited right in it: it is the most
           frequent change to a task, and it should not get a separate field in the page body. -->
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
        <!-- The tree is one level deep: a subtask cannot have subtasks of its own. -->
        <VBtn v-if="!task.parent" variant="text" :disabled="deleted" @click="addChild()">
          <template #prepend><IconPlus :size="16" /></template>
          {{ t('tasks.task.card.add_child') }}
        </VBtn>

        <!-- The rare stuff goes in the menu: purge is irreversible and belongs next to delete, not
             in one row with creating a subtask. -->
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
            <VListItem v-else :prepend-icon="IconRestore" :disabled="store.busy" @click="restore">
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
      <!-- The trash state is stated by a full-width banner, not a badge: while the task is
           deleted, neither its fields nor its status can be changed, and the person should learn
           that before running into a locked field. -->
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
          <!-- Where the task sits: a link to the parent. A root task has none — nowhere to go up. -->
          <button v-if="task.parent" type="button" class="task-page__parent" @click="goTask(task.parent.code)">
            <IconArrowUp :size="14" :stroke-width="1.6" />
            {{ task.parent.title }}
          </button>

          <!-- Every text card says in its header WHAT to write in this field, behind a "?" right
               after the title: the explanation is longer than a line and, read once, is not needed
               at every look. The hint sits in the header, not in the empty field, because it is
               needed not only when empty: a filled card without it does not say what was expected
               of it. An empty field shows the editor's own hint — how to add a block with the "/"
               command. -->
          <VCard variant="outlined" rounded="lg" class="task-page__card">
            <SectionHeader
              :title="t('tasks.task.detail.description')"
              :hint="t('tasks.task.detail.hint.description')"
            />
            <!-- The goal is one or two sentences, hence simple mode: paragraph, bold, italic. A
                 heading or table has no place in a goal, and the schema simply does not know them. -->
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

          <!-- Every task has context, even a simple one: it is "what you need to know to start",
               and without it a simple card shrinks to a single title line. -->
          <VCard variant="outlined" rounded="lg" class="task-page__card">
            <SectionHeader
              :title="t('tasks.task.detail.context')"
              :hint="t('tasks.task.detail.hint.context')"
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

          <!-- Constraints and acceptance criteria are the brief of a standard task. A simple one has
               none: there is nothing to deliver against criteria, and empty fields would only take
               up the screen. -->
          <VCard v-if="layout.brief" variant="outlined" rounded="lg" class="task-page__card">
            <SectionHeader
              :title="t('tasks.task.detail.constraints')"
              :hint="t('tasks.task.detail.hint.constraints')"
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
              :hint="t('tasks.task.detail.hint.criteria')"
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

          <!-- The agent's work, three cards in the order the work goes: the plan written before the
               code changes, the progress diary kept along the way, the result written at
               hand-over. Each answers its own question — intent, course, outcome — so they are
               separate cards and not sections of one text. -->
          <VCard v-if="layout.plan" variant="outlined" rounded="lg" class="task-page__card">
            <SectionHeader
              :title="t('tasks.task.detail.plan')"
              :hint="t('tasks.task.detail.hint.plan')"
            />
            <MarkdownEditor
              :model-value="draft.plan"
              :aria-label="t('tasks.task.detail.plan')"
              :max-length="TASK_PLAN_MAX"
              :readonly="deleted"
              :features="TASK_DOCUMENT_FEATURES"
              variant="plain"
              min-height="0"
              @update:model-value="(value) => { draft.plan = value; schedule() }"
              @blur="commit"
            />
          </VCard>

          <VCard v-if="layout.plan" variant="outlined" rounded="lg" class="task-page__card">
            <SectionHeader
              :title="t('tasks.task.detail.progress')"
              :hint="t('tasks.task.detail.hint.progress')"
            />
            <MarkdownEditor
              :model-value="draft.progress"
              :aria-label="t('tasks.task.detail.progress')"
              :max-length="TASK_PROGRESS_MAX"
              :readonly="deleted"
              :features="TASK_DOCUMENT_FEATURES"
              variant="plain"
              min-height="0"
              @update:model-value="(value) => { draft.progress = value; schedule() }"
              @blur="commit"
            />
          </VCard>

          <VCard v-if="layout.plan" variant="outlined" rounded="lg" class="task-page__card">
            <SectionHeader
              :title="t('tasks.task.detail.result')"
              :hint="t('tasks.task.detail.hint.result')"
            />
            <MarkdownEditor
              :model-value="draft.result"
              :aria-label="t('tasks.task.detail.result')"
              :max-length="TASK_RESULT_MAX"
              :readonly="deleted"
              :features="TASK_DOCUMENT_FEATURES"
              variant="plain"
              min-height="0"
              @update:model-value="(value) => { draft.result = value; schedule() }"
              @blur="commit"
            />
          </VCard>

          <!-- Stages and the journal are the rest of the work on the task, and they belong right
               under it: the plan promises, stages show progress, the journal keeps what came up on
               the way.
               Stages exist only on an extended task, and that is the only difference from a
               standard one: there the plan lives as prose above, and splitting it into steps with
               separate evidence only makes sense for work longer than one sitting. -->
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
            <SectionHeader :title="t('tasks.journal.section')" :count="task.journal.length" />
            <TaskJournal
              :task-code="task.code"
              :entries="task.journal"
              :disabled="deleted"
              @changed="reloadTask"
            />
          </section>

          <section>
            <SectionHeader :title="t('tasks.task.detail.children')" :count="task.children.length">
              <template #right>
                <VBtn
                  v-if="!task.parent"
                  variant="text"
                  size="small"
                  :disabled="deleted"
                  @click="addChild()"
                >
                  <template #prepend><IconPlus :size="16" /></template>
                  {{ t('tasks.task.card.add_child') }}
                </VBtn>
              </template>
            </SectionHeader>

            <!-- The branch under the task — in the same form as in the main list, with its own
                 search and toggles; each row opens ITS OWN page. -->
            <TaskSubtasksPanel
              ref="subtasks"
              :task-code="task.code"
              :workspace="task.workspace_code"
              :deleted="deleted"
              @open="goTask"
              @add-child="addChild"
            />
          </section>
        </div>

        <!-- The card is its own `aside`: a separate wrapper around it would add a level with
             nothing to live on it — the field column is this card. -->
        <VCard tag="aside" variant="outlined" rounded="lg" class="task-page__side">
          <!-- The group is optional: a task without one lands in the "No group" section, not lost.
               A workspace can have many groups, and they are recognised by look — an icon in the
               group's color, the same as in the task list. The search is pinned to the top of the
               menu and does not change the field.
               `:chips="false"` is mandatory: with chips Vuetify renders `#chip` and silently
               ignores `#selection`, so the selected group would be left without its icon. -->
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

          <!-- Status moves to its neighbours — from plan to work, from work to review — hence a
               field with steps, like priority's, and with an icon: the same one as in the task
               list row. -->
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

          <!-- The only assignable date: the day to finish by. The picked day is sent as the last
               second of that day (`formatDeadline`), otherwise a deadline "for today" would be
               overdue from the very morning. -->
          <!-- The calendar icon moves INSIDE the field: outside (`prepend-icon`, the VDateInput
               default) it stands as a separate box before the outline, and the field shifts right
               by 32px — noticeable in a column where all other fields start on one line. -->
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

          <!-- Type is picked with buttons: all three values are visible at once, without opening
               a list. The look comes from the design system — `outlined` + `divided`, the project
               default for `VBtnToggle` (plugins/vuetify.ts) and as shown in the showcase. The
               former `tonal` filled the selection with solid color, and the row read as a heavy
               bar.
               It comes last among the fields: type is set once at creation and changed less often
               than anything else in this column. -->
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

          <!-- Saving itself is not announced: every field saves on its own as it changes, and a
               "Saving…" line flashed on each pick. A failed save is — the person has to know the
               field did not land. It sits last in the column, so appearing it moves only the card's
               bottom edge, not the fields under the pointer. -->
          <p v-if="store.saveError" class="task-page__save-error">
            {{ store.saveError }}
          </p>
        </VCard>
      </div>
    </div>

    <!-- A field the person was editing was changed in the database meanwhile: the page already
         shows the database version, and what was typed is here so it can be copied. -->
    <TaskFieldConflictDialog v-model="conflictOpen" :items="conflictItems" />

    <TaskFormDialog
      v-model="formOpen"
      :workspace="task?.workspace_code ?? ''"
      :task="null"
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

/* The field column neither stretches nor shrinks: its width is set by the fields inside, and all
   the remaining space goes to the prose. Below 900px the columns stack — half a screen for the
   task text is no longer a reading column. */
/* 312px = 280px of fields + the card padding on both sides: the column gained a border, and the
   fields inside must keep the same width, otherwise the type toggle row would shrink another
   32px. */
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

/* Only text sections get a card. Stages, journal and subtasks stay on the canvas: each of their
   rows has its own border, and a card around them would give a frame within a frame.
   16px — between the filter panel (12px) and the group tile (18px): there are five cards in a row
   in this column, and every extra pixel of padding is multiplied by five.
   The frame-within-a-frame rule applies INSIDE the card too, so the prose fields are quiet
   (`quiet-field`, like the page title): a section has one frame — the card itself, and that a
   field is editable is shown by a background under the cursor and an outline on focus. */
.task-page__card {
  padding: 16px;
}

/* The field column stays in view while scrolling through long text: status and deadline are
   needed at any line of it, and fields that scrolled away would have to be found by scrolling
   back. It sticks only in the two-column layout — in one column a sticky strip would cover the
   text itself.
   The fields use the densest step (28px), while the spacing between them is, conversely, larger
   than usual: in a column of six fields in a row a taller box only takes space, and what tells
   the fields apart is the empty space around them. */
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

/* The floated label is set smaller than its value: the global `.v-field .v-label` rule from
   main.scss pins it to 13px and sits OUTSIDE the layers, so Vuetify's own scale (0.75em) does not
   reach it — the label comes out as tall as the value and in a narrow column reads as a second
   line of the field rather than its name. The upward shift puts it above the outline, on which
   Vuetify centres it. */
.task-page__side :deep(.v-field .v-label.v-field-label--floating) {
  font-size: 11px;
  transform: translateY(calc(-50% - 2px));
}

/* The link up is a button, not a `RouterLink`: the page owns the URL, and the markup must not
   know how it is built. It still looks like a link — it is a navigation. */
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

/* A borderless field: at rest it is text, under the cursor a background, on focus an accent
   outline. The padding matches that background, so entering edit mode does not shift a letter. */
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

/* The header's text half shrinks to its content: for an ordinary title that is exactly its length,
   for a field its own width, about 20 characters, which cannot fit even half a task name. It is
   stretched here, not in the shared `SectionHeader`: so far only the task has a field in a title. */
:deep(.section-header__text) {
  flex: 1 1 auto;
}

/* The title field stands IN PLACE of the page heading and must take exactly its line: the metrics
   are taken from the first-level heading, and the vertical padding is excluded from the height by
   a negative margin — otherwise the header would grow by the field's height and fall out of line
   with the headers of other pages. */
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

/* The code chip: a negative left margin takes its own padding out of the line — the copy icon
   aligns with the left edge of the title above it, and the hover background sticks out past the
   edge, like a button's. */
.task-page__code {
  margin-inline-start: -5px;
}

/* The edit status line sits above the fields and is silent at rest — it becomes a message only
   when an edit is in flight or failed to arrive. */
.task-page__save-error {
  margin: 0;
  font-size: 11px;
  color: var(--error);
}

/* The label sits closer to its field than the fields sit to each other — otherwise it reads as a
   heading for the whole block rather than an explanation of the field. */
.task-page__field {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

/* The group icon and name in the field sit in the same row as in a list item: the selected value
   is the same item, just shown in the field. */
.task-page__group-value {
  display: inline-flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
}

/* A button row has no floated label like the neighbouring fields, so its name is a line above it. */
.task-page__label {
  font-size: 12px;
  color: var(--text-muted);
}

/* The caption under the type explains behaviour rather than naming the field, so it is quieter
   than the label and sits BELOW the row, not above it. */
.task-page__hint {
  font-size: 11px;
  line-height: 1.4;
  color: var(--text-faint);
}

/* A button group's size is not inherited by its children (docs/conventions/frontend.md), so the
   height is set by hand: 26px plus the toggle's 1px outline top and bottom matches the neighbouring 28px fields,
   which use the dense step here. Labels of 11 characters split the column width evenly, so the
   font is one step smaller than a button's.
   The height goes through the variable: the group sets an inline `height: auto` on its buttons, and
   the global `.v-btn-group .v-btn` rule beats it with `height: var(--v-btn-height) !important`. */
.task-page__toggle { width: 100%; }

.task-page__toggle :deep(.v-btn) {
  flex: 1;
  min-width: 0;
  --v-btn-height: 26px;
  padding-inline: 6px;
  font-size: 12px;
  letter-spacing: 0;
  text-transform: none;
}

/* Timestamps go as "label / value" lines under the fields: they are not edited, and they share the
   space below the field column. */
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
