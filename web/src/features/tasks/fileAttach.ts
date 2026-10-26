// What a task's text field does with a file pasted or dropped into it (`MarkdownEditor`'s
// `attach`): the file goes to the task — to the stage or the note the field belongs to, when it
// does — and the field gets the file's code, `IMAGE@` for a picture, `FILE@` for the rest.
//
// The same bytes the task holds already are no failure here: a file is in a task once, and the
// field gets the code of the one the task has.
//
// A file over the storage's ceiling is refused before it is sent (`taskFileRefuse`, the field's and
// the files card's `refuse`), in the words the server would refuse it with.
//
// What a picture shown full screen on the task's page is called is the task's to edit
// (`taskFileEditor`, lent to the media panel): a deleted task's files are only read.
import { ApiError } from '@/api/client/internal'
import { FILE_TOO_LARGE } from '@/api/upload'
import type { FileBindingEditor } from '@/components/files/fileBinding'
import type { AttachFile, RefuseFile } from '@/components/markdown/editor/behavior'
import { fileQuote } from '@/components/markdown/shared/contracts'
import { useStorageStore } from '@/stores/storage'

import { detachTaskFile, updateTaskFile, uploadTaskFile, type TaskFilePlace } from './api'

const ALREADY_ATTACHED = 'tasks.file.already_attached'

export const taskFileRefuse: RefuseFile = (file) => useStorageStore().tooLarge(file, FILE_TOO_LARGE)

export function taskFileEditor(task: () => string, readonly: () => boolean): FileBindingEditor {
  return {
    save: async (file, patch) => { await updateTaskFile(task(), file, patch) },
    remove: async (file) => { await detachTaskFile(task(), file) },
    readonly,
  }
}

export function taskFileAttach(task: string, place?: TaskFilePlace): AttachFile {
  return async (file) => {
    try {
      const row = await uploadTaskFile(task, file, { place })
      return fileQuote(row.code, row.type)
    } catch (error) {
      if (error instanceof ApiError && error.code === ALREADY_ATTACHED && error.params?.file) {
        return fileQuote(String(error.params.file), String(error.params.type ?? ''))
      }
      throw error
    }
  }
}
