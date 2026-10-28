<script setup lang="ts">
// A codex record's print page — a note, or the codex itself with its rules — alone on a sheet
// (`PrintDocument`): the address the "PDF" button of the materials page prints in a hidden frame.
// Read only — nothing here edits the record.
import { computed, onActivated, ref } from 'vue'
import { useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'

import PrintDocument, { type PrintedDocument } from '@/components/PrintDocument.vue'
import { ApiError } from '@/api/client/internal'
import { errorText } from '@/api/errorText'
import { providePreviewWorkspace } from '@/stores/preview'
import { fmtDateTime } from '@/shared/utils/date'

import { getCodex, getNote, type CodexDetail, type CodexNote } from '../api'
import { displayPath } from '../paths'

const { t } = useI18n()
const route = useRoute()

const code = computed(() => String(route.params.code ?? '').toUpperCase())
// The workspace the materials page read the record in: the codes in it — and its files — resolve
// there. The print frame does not see that page, so the address carries it.
const workspace = computed(() => String(route.query.workspace ?? '') || undefined)

const record = ref<CodexDetail | CodexNote | null>(null)
const error = ref('')

providePreviewWorkspace(workspace, () => (record.value && 'path' in record.value ? record.value.code : undefined))

// A codex and its notes share the `CODEX@` prefix, and only the canvas tree tells them apart — the
// sheet has no tree. A note is what is printed far more often, so it is asked first and the codex
// only when no note has the code.
async function fetchRecord(target: string): Promise<CodexDetail | CodexNote> {
  try {
    return await getNote(target, { report: false })
  } catch (e) {
    if (e instanceof ApiError && e.status === 404) return getCodex(target, { report: false })
    throw e
  }
}

// The sheet is printed once, in a frame of its own, and loading here covers that one display.
// Opened in the app's own tab it may come back for another record: it starts empty then.
onActivated(async () => {
  record.value = null
  error.value = ''
  try {
    record.value = await fetchRecord(code.value)
  } catch (e) {
    error.value = errorText(e)
  }
})

const printed = computed<PrintedDocument | null>(() => {
  const row = record.value
  if (!row) return null
  // A codex's path is its own segment; a note's comes with it.
  const path = displayPath('path' in row ? row.path : row.segment)
  return {
    title: row.title,
    description: row.description,
    meta: [row.code, path, t('common.print.updated', { date: fmtDateTime(row.updated_at) })].filter(Boolean),
    body: row.body,
  }
})
</script>

<template>
  <PrintDocument :document="printed" :error="error" />
</template>
