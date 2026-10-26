<script setup lang="ts">
// A codex note's files — the shared files section (`AttachedFiles`) fed from the note: its list, its
// order, detaching. Only a note holds files, never the codex itself, so the editor draws this for
// a note alone.
//
// Read by the note's code, and read again when the change feed says a file of this note moved
// (`codex.file` carries the note in its refs). This tab's own edits do not come back through the
// feed: after a detach or an upload the list is read here; a reorder needs no read unless it was
// refused. This tab's own echoes are taken all the same: a file CREATED in the note's text field, a
// file UPDATED in the media panel of a picture shown full screen, a file DELETED from a picture's
// menu (a reorder or a detach of this section echoes too, and reads what the screen already shows).
//
// A file over the storage's ceiling is refused before it is sent (`noteFileRefuse`); the list counts
// as read (`ready`) only once this note's answer is in.
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'

import { ApiError } from '@/api/client/internal'
import { errorText } from '@/api/errorText'
import AttachedFiles, { type AttachedFile, type UploadFile } from '@/components/files/AttachedFiles.vue'
import { useChangeSubscription } from '@/composables/useChangeSubscription'
import type { Change } from '@/stores/changes'
import { useStorageStore } from '@/stores/storage'

import { detachNoteFile, listNoteFiles, reorderNoteFiles, uploadNoteFile, type NoteFileRow } from '../api'
import { noteFileRefuse } from '../fileAttach'

const props = defineProps<{
  noteCode: string
  /** The note is deleted: its files are kept for the restore, read but not moved or detached. */
  disabled?: boolean
}>()

const { t } = useI18n()

// The ceiling is read while the section is on screen, before anything is dropped on it.
useStorageStore()

const rows = ref<NoteFileRow[]>([])
const loaded = ref(false)

// A reply for a note the editor has already left is dropped: the same page opens note after note.
async function load(): Promise<void> {
  const note = props.noteCode
  const fresh = await listNoteFiles(note, { report: false }).catch(() => null)
  if (!fresh || note !== props.noteCode) return
  rows.value = fresh
  loaded.value = true
}

watch(() => props.noteCode, () => {
  rows.value = []
  loaded.value = false
  void load()
}, { immediate: true })

function concernsThisNote(change: Change): boolean {
  return change.ids.length === 0 || change.refs.includes(props.noteCode)
}

useChangeSubscription({
  entities: ['codex.file'],
  match: concernsThisNote,
  onChange: () => { void load() },
  onResync: () => { void load() },
  own: true,
})

const files = computed<AttachedFile[]>(() => rows.value.map((row) => ({
  code: row.code,
  title: row.title,
  description: row.description,
  originalName: row.original_filename + row.original_extension,
  mime: row.mime,
  size: row.size,
})))

async function reorder(codes: string[]): Promise<void> {
  try {
    await reorderNoteFiles(props.noteCode, codes)
  } catch {
    await load()
  }
}

async function detach(code: string): Promise<void> {
  try {
    await detachNoteFile(props.noteCode, code)
  } finally {
    await load()
  }
}

// The upload INTO one note, made once per note: a file queued on this note goes here even if the
// editor has opened another note by its turn (`AttachedFiles`, `uploadQueue.ts`).
function uploadInto(note: string): UploadFile {
  return async (file, progress) => {
    try {
      const row = await uploadNoteFile(note, file, { onProgress: (sent, total) => progress(total ? sent / total : 0) })
      if (note === props.noteCode) await load()
      return { ok: true, code: row.code }
    } catch (e) {
      if (e instanceof ApiError && e.code === 'codex.file.already_attached') {
        const held = e.params?.file ? String(e.params.file) : undefined
        return { ok: false, calm: true, code: held, text: t('codex.file.duplicate', { name: String(e.params?.name ?? file.name) }) }
      }
      return { ok: false, text: errorText(e) }
    }
  }
}

const upload = computed(() => uploadInto(props.noteCode))
</script>

<template>
  <AttachedFiles
    :files="files"
    :hint="t('codex.file.hint')"
    :disabled="disabled"
    :upload="upload"
    :holder="noteCode"
    :refuse="noteFileRefuse"
    :ready="loaded"
    :drop-note="t('codex.file.drop_note')"
    @reorder="reorder"
    @detach="detach"
  />
</template>
