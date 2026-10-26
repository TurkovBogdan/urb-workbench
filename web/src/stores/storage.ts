import { defineStore } from 'pinia'
import { ref, watch } from 'vue'

import { ApiError } from '@/api/client/internal'
import { errorText } from '@/api/errorText'
import { fetchFileSizeLimit } from '@/api/storage'
import { filesOverWindow } from '@/composables/useFileDrop'
import { overLimit } from '@/shared/utils/fileDrop'

// What the file storage will take, known before a file is sent: its size ceiling.
//
// The ceiling changes from the settings page without a restart, so it is read again every time files
// from the computer come over the window — before the drop that needs it — and once when the store
// is first used. Until the first answer it is unknown and nothing is refused here: the server's
// own check stays and refuses the file with the same words.
//
// The refusal is worded by the code the server would answer with (`core_storage_upload.file.too_large`),
// through `errorText`: the person reads the same sentence whichever side said no.
export const useStorageStore = defineStore('storage', () => {
  const maxFileSize = ref<number | null>(null)
  let reading: Promise<void> | null = null

  function refresh(): Promise<void> {
    reading ??= fetchFileSizeLimit()
      .then((limit) => { maxFileSize.value = limit })
      .catch(() => {})
      .finally(() => { reading = null })
    return reading
  }

  watch(filesOverWindow, (over) => { if (over) void refresh() })
  void refresh()

  /** The server's refusal of `file` under `code`, worded; `null` — within the ceiling, or unknown. */
  function tooLarge(file: File, code: string): string | null {
    const limit = maxFileSize.value
    if (limit === null || !overLimit(file.size, limit)) return null
    return errorText(new ApiError(413, {
      error: `The file is over the ${limit}-byte ceiling`,
      code,
      params: { limit, limit_mb: Math.floor(limit / (1024 * 1024)) },
    }))
  }

  return { maxFileSize, refresh, tooLarge }
})
