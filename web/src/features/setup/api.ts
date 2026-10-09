/**
 * API client for environment settings (backend: /internal/core/setup, module core_setup).
 *
 * Edits the ENV/.env layer: values are strings, applied by restarting the process
 * (PUT writes .env and triggers an os.execv restart). Separate from the runtime settings
 * (/core/settings), which apply hot.
 */

import { internalApi } from '@/api/client/internal'

export type SetupFieldType = 'str' | 'int' | 'bool' | 'choice'

export interface VisibleWhen {
  key: string
  equals: string
}

export interface SetupField {
  key: string
  type: SetupFieldType
  label: string
  description: string
  choices: string[]
  secret: boolean
  value: string
  visible_when: VisibleWhen | null
}

export interface SetupGroup {
  /** Machine code of the group — the key of its title in the form dictionary. */
  code: string
  /** English fallback title. */
  group: string
  fields: SetupField[]
}

export interface SetupPayload {
  groups: SetupGroup[]
}

/** A new listen address after the restart, next to the one it leaves. */
export interface ServerMove {
  host: string
  port: number
  from_host: string
  from_port: number
}

export interface ApplyResult {
  status: string
  applied: string[]
  /** `null` — the server comes back where it is now. */
  moves_to: ServerMove | null
}

const BASE = '/core/setup'

export async function getSetup(): Promise<SetupPayload> {
  return internalApi.get<SetupPayload>(BASE)
}

export async function applySetup(values: Record<string, string>): Promise<ApplyResult> {
  return internalApi.put<ApplyResult>(BASE, { values })
}

// Silent: it is polled while the server restarts, so every failed attempt is expected, and a toast
// per attempt would stack dozens of "network error" over the applying screen.
export async function isBackendUp(): Promise<boolean> {
  try {
    await internalApi.get('/health', { report: false })
    return true
  } catch {
    return false
  }
}
