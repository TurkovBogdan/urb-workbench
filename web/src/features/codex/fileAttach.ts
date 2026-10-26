// What a codex note's text field does with a file pasted or dropped into it (`MarkdownEditor`'s
// `attach`): the file goes to the note and the field gets its code, `IMAGE@` for a picture, `FILE@`
// for the rest. A codex itself holds no files, so its rules field gets no `attach`.
//
// The same bytes the note holds already are no failure here: the field gets the code of the file
// the note has.
//
// A file over the storage's ceiling is refused before it is sent (`noteFileRefuse`, the field's and
// the files card's `refuse`), in the words the server would refuse it with.
//
// What a picture shown full screen on the note's page is called is the note's to edit
// (`noteFileEditor`, lent to the media panel): a deleted note's files are only read.
import { ApiError } from '@/api/client/internal'
import { FILE_TOO_LARGE } from '@/api/upload'
import type { FileBindingEditor } from '@/components/files/fileBinding'
import type { AttachFile, RefuseFile } from '@/components/markdown/editor/behavior'
import { fileQuote } from '@/components/markdown/shared/contracts'
import { useStorageStore } from '@/stores/storage'

import { detachNoteFile, updateNoteFile, uploadNoteFile } from './api'

const ALREADY_ATTACHED = 'codex.file.already_attached'

export const noteFileRefuse: RefuseFile = (file) => useStorageStore().tooLarge(file, FILE_TOO_LARGE)

/** `note` — the note on the page, `null` while none is: then nothing is edited. */
export function noteFileEditor(note: () => string | null, readonly: () => boolean): FileBindingEditor {
  return {
    save: async (file, patch) => {
      const holder = note()
      if (holder) await updateNoteFile(holder, file, patch)
    },
    remove: async (file) => {
      const holder = note()
      if (holder) await detachNoteFile(holder, file)
    },
    readonly: () => !note() || readonly(),
  }
}

export function noteFileAttach(note: string): AttachFile {
  return async (file) => {
    try {
      const row = await uploadNoteFile(note, file)
      return fileQuote(row.code, row.type)
    } catch (error) {
      if (error instanceof ApiError && error.code === ALREADY_ATTACHED && error.params?.file) {
        return fileQuote(String(error.params.file), String(error.params.type ?? ''))
      }
      throw error
    }
  }
}
