/**
 * HTTP API client of the settings subsystem (backend: /internal/core/settings).
 *
 * Field descriptions follow the shared contract `shared/settings-fields.ts`. Values are stored in
 * the module as a `key → value` object; on PUT we send the raw value, the backend validates it.
 */

import { internalApi } from '@/api/client/internal'
import type { FieldDescriptor } from '@/shared/settings-fields'

export interface ModulePayload {
  module: string
  description: string
  fields: FieldDescriptor[]
  values: Record<string, unknown>
}

const BASE = '/core/settings'

export async function listModules(): Promise<ModulePayload[]> {
  return internalApi.get<ModulePayload[]>(`${BASE}/modules`)
}

export async function putValue(
  module: string,
  key: string,
  value: unknown,
): Promise<Record<string, unknown>> {
  const data = await internalApi.put<{ values: Record<string, unknown> }>(
    `${BASE}/${module}/${key}`,
    { value },
  )
  return data.values
}

export async function resetValue(
  module: string,
  key: string,
): Promise<Record<string, unknown>> {
  const data = await internalApi.post<{ values: Record<string, unknown> }>(
    `${BASE}/${module}/${key}/reset`,
  )
  return data.values
}
