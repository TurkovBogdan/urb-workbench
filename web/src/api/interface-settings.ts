// Interface settings client (backend: /internal/core/interface). Values arrive effective — the
// default wherever the person changed nothing — so the frontend has nothing to fill in.
//
// All four calls are silent (`report: false`): by the time of the request the value is already
// applied on screen, and a toast per setting would be pointless noise. A persistent failure is
// reported by the sync mechanism itself — `shared/utils/settings-sync`.
import { internalApi } from '@/api/client/internal'

export type SettingType = 'string' | 'number' | 'boolean'

export type SettingValue = string | number | boolean

/** Machine description of a field: the client picks the control by it. */
export interface SettingSchema {
  key: string
  type: SettingType
  default: SettingValue
  /** Set of allowed values; `null` — only the type is constrained. */
  options: SettingValue[] | null
}

export interface SettingsPayload {
  values: Record<string, SettingValue>
  /** Arrives only on the startup request (`include_schema`). */
  schema?: SettingSchema[] | null
}

const BASE = '/core/interface/settings'

const SILENT = { report: false } as const

export function fetchSettings(includeSchema = false): Promise<SettingsPayload> {
  return internalApi.get<SettingsPayload>(BASE, {
    ...SILENT,
    query: includeSchema ? { include_schema: true } : undefined,
  })
}

export function saveSettings(values: Record<string, SettingValue>): Promise<SettingsPayload> {
  return internalApi.patch<SettingsPayload>(BASE, { values }, SILENT)
}

/** Reset to default: the rows disappear, the response carries the values that replaced them. */
export function resetSettings(keys: string[]): Promise<SettingsPayload> {
  return internalApi.post<SettingsPayload>(`${BASE}/reset`, { keys }, SILENT)
}
