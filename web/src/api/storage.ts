// The file storage's size ceiling — `core_storage`'s setting `max_file_size_mb`, read from the
// module settings route the settings page reads (`/internal/core/settings/<module>`): a read-only
// GET that already answers with the current value, so no route of its own is needed.
//
// Silent (`report: false`): without the ceiling the page sends the file and the server refuses an
// oversize one itself — a toast about the read would be louder than the loss.
import { internalApi } from '@/api/client/internal'

const STORAGE_SETTINGS = '/core/settings/core_storage'
const BYTES_PER_MB = 1024 * 1024

interface ModuleSettings {
  values: Record<string, unknown>
}

/** The ceiling in bytes, as the server counts it; `null` — the setting is not there. */
export async function fetchFileSizeLimit(): Promise<number | null> {
  const settings = await internalApi.get<ModuleSettings>(STORAGE_SETTINGS, { report: false })
  const megabytes = Number(settings.values.max_file_size_mb)
  return Number.isFinite(megabytes) && megabytes > 0 ? megabytes * BYTES_PER_MB : null
}
