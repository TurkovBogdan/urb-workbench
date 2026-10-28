<script setup lang="ts">
// A task note's print page: the note alone on a sheet (`PrintDocument`), the address the "PDF"
// button of the note page prints in a hidden frame. Read only — nothing here edits the note.
import { computed, onActivated, ref } from 'vue'
import { useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'

import PrintDocument, { type PrintedDocument } from '@/components/PrintDocument.vue'
import { errorText } from '@/api/errorText'
import { providePreviewWorkspace } from '@/stores/preview'
import { fmtDateTime } from '@/shared/utils/date'

import { getTask, getTaskNote, type TaskDetail, type TaskNoteDetail } from '../api'

const { t } = useI18n()
const route = useRoute()

const taskCode = computed(() => String(route.params.code ?? '').toUpperCase())
const noteCode = computed(() => String(route.params.note ?? '').toUpperCase())

const note = ref<TaskNoteDetail | null>(null)
const task = ref<TaskDetail | null>(null)
const error = ref('')

// The codes in the note read as on its page: in its task's workspace, its files named as the task
// names them.
providePreviewWorkspace(() => task.value?.workspace_code, taskCode)

// The sheet is printed once, in a frame of its own, and loading here covers that one display.
// Opened in the app's own tab it may come back for another note: it starts empty then, not with
// the previous one.
onActivated(async () => {
  note.value = null
  task.value = null
  error.value = ''
  try {
    const [row, owner] = await Promise.all([
      getTaskNote(taskCode.value, noteCode.value, { report: false }),
      getTask(taskCode.value, { report: false }),
    ])
    task.value = owner
    note.value = row
  } catch (e) {
    error.value = errorText(e)
  }
})

const printed = computed<PrintedDocument | null>(() => {
  if (!note.value || !task.value) return null
  return {
    title: note.value.title,
    description: note.value.description,
    meta: [
      note.value.code,
      t('tasks.note.print_of_task', { title: task.value.title, code: task.value.code }),
      t('common.print.updated', { date: fmtDateTime(note.value.updated_at) }),
    ],
    body: note.value.body,
  }
})
</script>

<template>
  <PrintDocument :document="printed" :error="error" />
</template>
