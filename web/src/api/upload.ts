// A file into whatever holds it — the file upload module (`core_storage_upload`): one address for
// every holder, `POST /storage/upload?holder=<CODE>`, the body the file as is. The holder's code
// says where it goes (`TASK@`, `NOTE@`, `STAGE@`, `CODEX@`), and the answer is the file as that
// holder's list shows it, so the caller names the row type.
//
// The refusals are `ApiError`s: the module's own codes (`core_storage_upload.file.too_large`, a name
// the storage could not keep, an unknown holder) and the holder's (`tasks.file.already_attached`…),
// with the holder's `params`.
import { storageUpload, type UploadOptions } from '@/api/client/storage'

export const FILE_TOO_LARGE = 'core_storage_upload.file.too_large'

export function uploadFile<T>(holder: string, file: File, opts: Omit<UploadOptions, 'query'> = {}): Promise<T> {
  return storageUpload<T>('/upload', file, { ...opts, query: { holder, filename: file.name } })
}

export type { UploadOptions }
