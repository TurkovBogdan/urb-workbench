<script setup lang="ts">
// The task's files — the shared files section (`AttachedFiles`) fed from the task: its list, its
// order, detaching, and where in the task each file was attached (a note or a stage — named by
// what the page already holds of them).
//
// The list is not part of the task's response: it is read here, by the task's code, and read again
// when the change feed says a file of this task moved (`tasks.file` carries the task in its refs —
// the agent attached one, another tab reordered them). This tab's own edits do not come back
// through the feed, so after a detach or an upload the list is read here; a reorder needs no read —
// the screen already shows what was sent, and only a refused one re-reads to show the real order.
// This tab's own echoes are taken all the same, news from elsewhere on the page: a file CREATED there
// — dropped or pasted into a field of the task —, a file UPDATED there — renamed in the media panel
// of a picture shown full screen —, a file DELETED there — from a picture's menu. A reorder or a
// detach of this section echoes too: the read shows what the screen already shows.
//
// The section uploads into the task as a whole: a stage's or a note's file comes from that stage's or
// note's own field, which knows its place. A file over the storage's ceiling is refused before it is
// sent (`taskFileRefuse`); the list counts as read (`ready`) only once this task's answer is in, so
// the section does not take a list loading for files that just arrived.
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'

import { ApiError } from '@/api/client/internal'
import { errorText } from '@/api/errorText'
import AttachedFiles, { type AttachedFile, type UploadFile } from '@/components/files/AttachedFiles.vue'
import { useChangeSubscription } from '@/composables/useChangeSubscription'
import type { Change } from '@/stores/changes'
import { useStorageStore } from '@/stores/storage'

import { taskFileRefuse } from '../fileAttach'
import {
  detachTaskFile,
  listTaskFiles,
  reorderTaskFiles,
  uploadTaskFile,
  type StageRow,
  type TaskFileRow,
  type TaskNoteRow,
} from '../api'

const props = defineProps<{
  taskCode: string
  notes: TaskNoteRow[]
  stages: StageRow[]
  /** The task is deleted: its files are read, not moved or detached. */
  disabled?: boolean
}>()

const { t } = useI18n()

// The ceiling is read while the section is on screen, before anything is dropped on it.
useStorageStore()

const rows = ref<TaskFileRow[]>([])
const loaded = ref(false)

// A reply for a task the page has already left is dropped: the code may change while the request
// is in flight (moving between tasks keeps the same page).
async function load(): Promise<void> {
  const task = props.taskCode
  const fresh = await listTaskFiles(task, { report: false }).catch(() => null)
  if (!fresh || task !== props.taskCode) return
  rows.value = fresh
  loaded.value = true
}

watch(() => props.taskCode, () => {
  rows.value = []
  loaded.value = false
  void load()
}, { immediate: true })

function concernsThisTask(change: Change): boolean {
  return change.ids.length === 0 || change.refs.includes(props.taskCode)
}

useChangeSubscription({
  entities: ['tasks.file'],
  match: concernsThisTask,
  onChange: () => { void load() },
  onResync: () => { void load() },
  own: true,
})

function placeOf(row: TaskFileRow): string {
  if (row.note_code) {
    const note = props.notes.find((one) => one.code === row.note_code)
    return note ? t('tasks.file.place.note', { title: note.title }) : ''
  }
  if (row.stage_code) {
    const stage = props.stages.find((one) => one.code === row.stage_code)
    return stage ? t('tasks.file.place.stage', { number: stage.number, title: stage.title }) : ''
  }
  return ''
}

const files = computed<AttachedFile[]>(() => rows.value.map((row) => ({
  code: row.code,
  title: row.title,
  description: row.description,
  originalName: row.original_filename + row.original_extension,
  mime: row.mime,
  size: row.size,
  place: placeOf(row),
})))

// The files of the task's notes and of its stages stay out of sight until their switch says
// otherwise: they are those places' material, and in the task's own list they would crowd out the
// files the task itself holds — those are always shown. The switches belong to the page and are
// not remembered, as the journal's "open only" is. A switch with nothing to show is not drawn: with
// no notes' or stages' files there is nothing it would hide.
const withNotes = ref(false)
const withStages = ref(false)
const noteFiles = computed(() => new Set(rows.value.filter((row) => row.note_code).map((row) => row.code)))
const stageFiles = computed(() => new Set(rows.value.filter((row) => row.stage_code).map((row) => row.code)))
const shows = computed(() => {
  if (withNotes.value && withStages.value) return undefined
  return (file: AttachedFile) =>
    (withNotes.value || !noteFiles.value.has(file.code)) && (withStages.value || !stageFiles.value.has(file.code))
})

async function reorder(codes: string[]): Promise<void> {
  try {
    await reorderTaskFiles(props.taskCode, codes)
  } catch {
    await load()
  }
}

async function detach(code: string): Promise<void> {
  try {
    await detachTaskFile(props.taskCode, code)
  } finally {
    await load()
  }
}

// The upload INTO one task, made once per task: a file queued on this task goes here even if the
// page has moved on to another task by its turn (`AttachedFiles`, `uploadQueue.ts`).
function uploadInto(task: string): UploadFile {
  return async (file, progress) => {
    try {
      const row = await uploadTaskFile(task, file, { onProgress: (sent, total) => progress(total ? sent / total : 0) })
      if (task === props.taskCode) await load()
      return { ok: true, code: row.code }
    } catch (e) {
      if (e instanceof ApiError && e.code === 'tasks.file.already_attached') {
        const held = e.params?.file ? String(e.params.file) : undefined
        return { ok: false, calm: true, code: held, text: t('tasks.file.duplicate', { name: String(e.params?.name ?? file.name) }) }
      }
      return { ok: false, text: errorText(e) }
    }
  }
}

const upload = computed(() => uploadInto(props.taskCode))
</script>

<template>
  <AttachedFiles
    :files="files"
    :hint="t('tasks.file.hint')"
    :disabled="disabled"
    :upload="upload"
    :holder="taskCode"
    :refuse="taskFileRefuse"
    :ready="loaded"
    :shows="shows"
    :drop-note="t('tasks.file.drop_note')"
    @reorder="reorder"
    @detach="detach"
  >
    <template #actions>
      <VSwitch
        v-if="noteFiles.size"
        v-model="withNotes"
        :label="t('tasks.file.with_notes', { count: noteFiles.size })"
        color="primary"
        density="compact"
        hide-details
        class="task-files__switch task-files__notes"
      />
      <VSwitch
        v-if="stageFiles.size"
        v-model="withStages"
        :label="t('tasks.file.with_stages', { count: stageFiles.size })"
        color="primary"
        density="compact"
        hide-details
        class="task-files__switch task-files__stages"
      />
    </template>
  </AttachedFiles>
</template>

<style scoped>
/* As the journal's "open only": the switch's 40px box is its touch target, not its look, so the
   extra height is taken out of the header's flow; off, its label steps back. */
.task-files__switch {
  flex: none;
  margin-block: -7px;
}

/* A switch's track would otherwise run into the label before it, and the two read as one control. */
.task-files__switch + .task-files__switch {
  margin-inline-start: 12px;
}

.task-files__switch :deep(.v-selection-control:not(.v-selection-control--dirty) .v-label) {
  opacity: var(--v-medium-emphasis-opacity);
}
</style>
