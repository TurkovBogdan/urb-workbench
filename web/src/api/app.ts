// Process-level switches (backend: /internal/core/app). They come from `.env` and change only with
// a restart, so one read per page load is enough.
//
// Silent (`report: false`): a failure here costs a hidden menu section, and a toast about it would
// be louder than the loss. The caller keeps the defaults instead.
import { internalApi } from '@/api/client/internal'

export interface AppFlags {
  dev_mode: boolean
}

export function fetchAppFlags(): Promise<AppFlags> {
  return internalApi.get<AppFlags>('/core/app', { report: false })
}
