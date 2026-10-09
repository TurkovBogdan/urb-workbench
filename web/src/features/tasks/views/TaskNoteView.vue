<script setup lang="ts">
// A task note — a PAGE at `/tasks/task/TASK@…/note/NOTE@…`, inside its task's.
//
// A page rather than a dialog: a note is a document — sections, tables, diagrams, up to 64K — that
// the person and the agent both edit, and it needs the room, an address the agent can open
// (`interface_open(NOTE@)`), and to survive a reload. It sits inside the task's address because
// only the task knows whose note it is: the way back leads there.
//
// Editing works as on the task page, and for the same reasons (see `TaskView.vue`, "Field draft"):
// fields are edited in place and save themselves after a typing pause and on leaving the field;
// the page keeps its own draft and the version it was taken from, merges what the agent writes
// meanwhile, and on a clash lets the database win and hands back what the person typed. Only the
// fields that changed are sent.
import { computed, onActivated, onBeforeUnmount, onDeactivated, reactive, ref, watch } from 'vue'
import { onBeforeRouteLeave, useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { IconRefresh } from '@tabler/icons-vue'

import PageLayout from '@/layout/templates/PageLayout.vue'
import PageHeader from '@/layout/components/PageHeader.vue'
import CopyChip from '@/components/CopyChip.vue'
import InvisibleField from '@/components/InvisibleField.vue'
import { MarkdownEditor } from '@/components/markdown/editor'
import SectionError from '@/components/SectionError.vue'
import SectionHeader from '@/components/SectionHeader.vue'
import { errorText } from '@/api/errorText'
import { useChangeSubscription } from '@/composables/useChangeSubscription'
import type { Change } from '@/stores/changes'
import { NOTE_BODY_MAX, NOTE_DESCRIPTION_MAX, NOTE_TITLE_MAX } from '@/features/notes/labels'

import TaskFieldConflictDialog from '../components/TaskFieldConflictDialog.vue'
import { getTask, getTaskNote, patchTaskNote, type TaskDetail, type TaskNoteDetail, type TaskNotePatch } from '../api'
import { TASK_DOCUMENT_FEATURES } from '../editor'

/** Silence in a field after which the typed text is sent — the same pause as on the task page. */
const TYPING_PAUSE = 700

const ROUTE_NAME = 'tasks-task-note'

const { t } = useI18n()
const route = useRoute()

const taskCode = computed(() => String(route.params.code ?? '').toUpperCase())
const noteCode = computed(() => String(route.params.note ?? '').toUpperCase())

const note = ref<TaskNoteDetail | null>(null)
const task = ref<TaskDetail | null>(null)
const loading = ref(false)
const error = ref<unknown>(null)
const saveError = ref<string | null>(null)

/** Read, not written: the task is in the trash, and the backend refuses its notes' edits. */
const readonly = computed(() => Boolean(task.value?.deleted_at))
const taskPath = computed(() => `/tasks/task/${encodeURIComponent(taskCode.value)}`)

// ── Loading ───────────────────────────────────────────────────────────────────
// The page lives in KeepAlive: `onActivated` covers both the first display and every return.
let active = false
let current = ''

async function load(): Promise<void> {
  const wanted = `${taskCode.value}/${noteCode.value}`
  current = wanted
  loading.value = true
  error.value = null
  try {
    const [row, owner] = await Promise.all([
      getTaskNote(taskCode.value, noteCode.value, { report: false }),
      getTask(taskCode.value, { report: false }),
    ])
    if (current !== wanted) return
    task.value = owner
    note.value = row
  } catch (e) {
    if (current !== wanted) return
    error.value = e
    note.value = null
  } finally {
    if (current === wanted) loading.value = false
  }
}

onActivated(() => {
  active = true
  void load()
})

onDeactivated(() => { active = false })

// Another note while the page is on screen: KeepAlive keeps one instance and does not reactivate it.
watch(
  () => [route.params.code, route.params.note],
  () => {
    if (!active || route.name !== ROUTE_NAME || !route.params.note) return
    void load()
  },
)

// ── Draft ─────────────────────────────────────────────────────────────────────
const FIELDS = ['title', 'description', 'body'] as const
type Field = (typeof FIELDS)[number]
type Snapshot = Record<Field, string>

const draft = reactive<Snapshot>({ title: '', description: '', body: '' })

function snapshotOf(row: TaskNoteDetail | null): Snapshot {
  return { title: row?.title ?? '', description: row?.description ?? '', body: row?.body ?? '' }
}

/** The title is sent trimmed, so it is compared trimmed. */
function draftValue(field: Field): string {
  return field === 'title' ? draft.title.trim() : draft[field]
}

let base: Snapshot = snapshotOf(null)

interface FieldConflict { field: Field; mine: string }
const conflicts = ref<FieldConflict[]>([])
const conflictOpen = computed({
  get: () => conflicts.value.length > 0,
  set: (open: boolean) => { if (!open) conflicts.value = [] },
})

const FIELD_LABELS: Record<Field, string> = {
  title: 'tasks.note.title',
  description: 'tasks.note.description',
  body: 'tasks.note.body',
}

const conflictItems = computed(() =>
  conflicts.value.map((conflict) => ({ label: t(FIELD_LABELS[conflict.field]), text: conflict.mine })),
)

function fillDraft(row: TaskNoteDetail | null): void {
  Object.assign(draft, snapshotOf(row))
  base = snapshotOf(row)
  conflicts.value = []
}

/** Merge a fresh read: untouched fields follow the database, a clash lets the database win. */
function merge(row: TaskNoteDetail): void {
  const remote = snapshotOf(row)
  const found: FieldConflict[] = []
  for (const field of FIELDS) {
    if (remote[field] === base[field]) continue
    const mine = draftValue(field)
    if (mine !== base[field] && mine !== remote[field]) found.push({ field, mine })
    draft[field] = remote[field]
  }
  base = remote
  if (found.length) conflicts.value = [...conflicts.value, ...found]
}

watch(note, (next, prev) => {
  if (!next || !prev || next.code !== prev.code) fillDraft(next)
  else merge(next)
})

// ── Saving ────────────────────────────────────────────────────────────────────
let timer: ReturnType<typeof setTimeout> | null = null
let saving: Promise<unknown> = Promise.resolve()

function stopTimer(): void {
  if (timer === null) return
  clearTimeout(timer)
  timer = null
}

/** Send what changed since `base`; `base` moves first so the echo of our own save is not a clash. */
async function commit(): Promise<void> {
  stopTimer()
  const row = note.value
  if (!row || readonly.value) return
  const body: TaskNotePatch = {}
  const fields: Field[] = []
  for (const field of FIELDS) {
    const value = draftValue(field)
    if (value === base[field]) continue
    // An empty title is not saved: the card would be a blank line in the task's list.
    if (field === 'title' && !value) continue
    fields.push(field)
    body[field] = value
  }
  if (!fields.length) return
  const before = { ...base }
  for (const field of fields) base[field] = draftValue(field)
  const request = patchTaskNote(taskCode.value, row.code, body, { report: false })
  saving = request
  try {
    note.value = await request
    saveError.value = null
  } catch (e) {
    for (const field of fields) base[field] = before[field]
    saveError.value = errorText(e)
  }
}

function schedule(): void {
  stopTimer()
  timer = setTimeout(() => { timer = null; void commit() }, TYPING_PAUSE)
}

onBeforeUnmount(stopTimer)
onBeforeRouteLeave(() => { void commit() })

// ── Live updates ──────────────────────────────────────────────────────────────
// The agent edits a note by parts (`content_*`) and renames it (`task_note_update`): the document
// changes as `notes.note`. The task's own changes matter too — a deleted task makes the note read-only.
function concernsThisNote(change: Change): boolean {
  if (change.ids.length === 0) return true
  if (change.entity === 'tasks.task') return change.ids.includes(taskCode.value)
  return change.ids.includes(note.value?.code ?? noteCode.value)
}

async function reloadLive(): Promise<void> {
  await saving
  await load()
}

useChangeSubscription({
  entities: ['notes.note', 'tasks.note', 'tasks.task'],
  match: concernsThisNote,
  onChange: () => { void reloadLive() },
  onResync: () => { void reloadLive() },
  reloadsOnReturn: true,
})

const refreshing = ref(false)

async function refresh(): Promise<void> {
  refreshing.value = true
  try {
    await commit()
    await load()
  } finally {
    refreshing.value = false
  }
}
</script>

<template>
  <PageLayout>
    <PageHeader :title="note?.title || t('tasks.note.page_title')" :back-to="taskPath">
      <template v-if="note" #title>
        <InvisibleField
          :model-value="draft.title"
          :placeholder="t('tasks.note.title')"
          :aria-label="t('tasks.note.title')"
          :maxlength="NOTE_TITLE_MAX"
          :disabled="readonly"
          :error="!draft.title.trim()"
          class="note-page__title"
          @update:model-value="(value) => { draft.title = value; schedule() }"
          @blur="commit"
        />
      </template>

      <template v-if="note" #description>
        <CopyChip :text="note.code" :hint="t('common.action.copy_code')" class="note-page__code" />
      </template>

      <template v-if="note" #actions>
        <VBtn variant="text" :disabled="refreshing" @click="refresh">
          <template #prepend><IconRefresh :size="16" :class="{ 'icon-spin': refreshing }" /></template>
          {{ t('common.action.refresh') }}
        </VBtn>
      </template>
    </PageHeader>

    <SectionError v-if="error" :error="error" />

    <div v-else-if="loading && !note" class="note-page__loading">
      <VProgressCircular indeterminate size="28" width="3" />
    </div>

    <div v-else-if="note" class="note-page">
      <VAlert v-if="readonly" type="warning" variant="tonal" density="compact">
        {{ t('tasks.note.task_deleted') }}
      </VAlert>

      <div class="note-page__grid">
        <div class="note-page__main">
          <VCard variant="outlined" rounded="lg" class="note-page__card">
            <SectionHeader :title="t('tasks.note.description')" :hint="t('tasks.note.hint.description')" />
            <MarkdownEditor
              :model-value="draft.description"
              :aria-label="t('tasks.note.description')"
              :max-length="NOTE_DESCRIPTION_MAX"
              :readonly="readonly"
              mode="simple"
              variant="plain"
              min-height="0"
              @update:model-value="(value) => { draft.description = value; schedule() }"
              @blur="commit"
            />
          </VCard>

          <VCard variant="outlined" rounded="lg" class="note-page__card">
            <SectionHeader :title="t('tasks.note.body')" :hint="t('tasks.note.hint.body')" />
            <MarkdownEditor
              :model-value="draft.body"
              :aria-label="t('tasks.note.body')"
              :max-length="NOTE_BODY_MAX"
              :readonly="readonly"
              :features="TASK_DOCUMENT_FEATURES"
              variant="plain"
              min-height="240px"
              @update:model-value="(value) => { draft.body = value; schedule() }"
              @blur="commit"
            />
          </VCard>
        </div>

        <VCard tag="aside" variant="outlined" rounded="lg" class="note-page__side">
          <div class="note-page__field">
            <span class="note-page__label">{{ t('tasks.note.task') }}</span>
            <RouterLink :to="taskPath" class="note-page__task">{{ task?.title || taskCode }}</RouterLink>
          </div>

          <!-- Last in the column, as on the task page: appearing, it moves only the card's bottom edge. -->
          <p v-if="saveError" class="note-page__save-error">{{ saveError }}</p>
        </VCard>
      </div>
    </div>

    <TaskFieldConflictDialog v-model="conflictOpen" :items="conflictItems" />
  </PageLayout>
</template>

<style scoped>
.note-page {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.note-page__loading {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 200px;
}

/* The grid and the side column are the task page's, so going from a task to its note keeps the
   frame in place. */
.note-page__grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 312px;
  gap: 28px;
  align-items: start;
}

@media (max-width: 900px) {
  .note-page__grid { grid-template-columns: minmax(0, 1fr); gap: 20px; }
}

.note-page__main {
  display: flex;
  flex-direction: column;
  gap: 16px;
  min-width: 0;
}

.note-page__card { padding: 16px; }

.note-page__side {
  display: flex;
  flex-direction: column;
  gap: 18px;
  min-width: 0;
  padding: 16px;
  position: sticky;
  top: 0;
}

@media (max-width: 900px) {
  .note-page__side { position: static; }
}

.note-page__field {
  display: flex;
  flex-direction: column;
  gap: 6px;
  min-width: 0;
}

.note-page__label {
  font-size: 12px;
  color: var(--text-muted);
}

/* As on the task page: the header's text half would shrink to the line under the title, and the
   title field with it. */
:deep(.section-header__text) {
  flex: 1 1 auto;
}

.note-page__title {
  width: 100%;
}

.note-page__title :deep(.v-field__input) {
  min-height: 28px;
  padding-block: 4px;
  margin-block: -4px;
  font-size: 22px;
  font-weight: 700;
  line-height: 28px;
}

/* The chip's own padding is taken out of the line, as on the task page: the copy icon aligns with
   the title's left edge. */
.note-page__code {
  margin-inline-start: -5px;
}

.note-page__task {
  font-size: 13px;
  line-height: 18px;
  color: var(--text);
  text-decoration: none;
  overflow-wrap: anywhere;
}

.note-page__task:hover { text-decoration: underline; }

.note-page__save-error {
  margin: 0;
  font-size: 11px;
  color: var(--error);
}
</style>
