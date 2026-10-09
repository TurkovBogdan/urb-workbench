// Syncing interface settings with the database: hydration, queue, debounce and the "applying from
// outside" flag. All the network logic is gathered here rather than smeared over the store — the
// store stays a set of refs.
//
// The rule everything else follows from: the database is the source of truth, localStorage stays a
// cache. The cache paints the page before the first frame, so a request at that point would mean a
// flash of the wrong styling; hydration runs AFTER mount and blocks nothing (a backend raised by
// the MCP shim doesn't answer right away, and a blocking request would turn startup into a frozen
// splash).
import { ref, type Ref } from 'vue'

import { ApiError } from '@/api/client/internal'
import {
  fetchSettings,
  resetSettings,
  saveSettings,
  type SettingSchema,
  type SettingValue,
} from '@/api/interface-settings'
import { pushToast } from '@/composables/useToasts'
import { i18n } from '@/plugins/i18n'
import type { Codec } from './persisted'

/** Service cache keys contain a dot — registry settings don't, so they can't be confused. */
const PENDING_KEY = 'sync.pending'
const IMPORT_MARKER = 'sync.imported'

const DEBOUNCE_MS = 450

/** How many failed sends in a row we tolerate silently before telling the person. */
const FAILURES_BEFORE_TOAST = 3

/** Old dotted names in the browser cache → registry keys. Needed exactly once, during migration. */
const LEGACY_KEYS: Record<string, string> = {
  'app.theme': 'interface_theme',
  'app.font.interface': 'interface_font',
  'app.font.reading': 'interface_font_reading',
  'app.font.reading_size': 'interface_font_reading_size',
  'app.font.reading_measure': 'interface_font_reading_measure',
  'app.font.mono': 'interface_font_mono',
  'app.font.diagram': 'interface_font_diagram',
  'app.diagram.align': 'interface_diagram_align',
  'app.diagram.max_height': 'interface_diagram_max_height',
  'app.sidebar_collapsed': 'interface_sidebar_collapsed',
}

interface Synced {
  state: Ref<SettingValue>
  fallback: SettingValue
  codec: Codec<never>
}

const synced = new Map<string, Synced>()
const pending = new Set<string>(pendingFromCache())

/** Field schema: type, default and the set of allowed values. Empty until hydration arrives. */
export const settingsSchema = ref<SettingSchema[]>([])

let applyingExternal = false
let sending = false
let failures = 0
let timer: ReturnType<typeof setTimeout> | undefined

export function registerSetting<T extends SettingValue>(
  key: string,
  state: Ref<T>,
  fallback: T,
  codec: Codec<T>,
): void {
  synced.set(key, {
    state: state as Ref<SettingValue>,
    fallback,
    codec: codec as unknown as Codec<never>,
  })
}

/** Applying a value from the database: a ref change at this moment must not be sent back. */
export function isApplyingExternal(): boolean {
  return applyingExternal
}

export function enqueue(key: string): void {
  pending.add(key)
  writePending()
  schedule()
}

function schedule(): void {
  clearTimeout(timer)
  timer = setTimeout(() => void flush(), DEBOUNCE_MS)
}

/**
 * Send what has accumulated. Changed values go as a map, ones returned to the default as a reset
 * list: a row equal to the default is not stored in the database.
 *
 * The queue is cleared only after success. A failure doesn't pop up per setting — the value is
 * already applied, the person has nothing to fix; a persistent failure is reported once.
 *
 * What the server rejected is dropped from the queue right away: the batch applies as a whole, so
 * one invalid value (a corrupted cache, a set narrowed since the last deploy) would hold every
 * other key in the queue too — forever, with a toast every third attempt.
 */
export async function flush(): Promise<void> {
  if (sending || pending.size === 0) return
  const sent = new Map<string, SettingValue>()
  const values: Record<string, SettingValue> = {}
  const resets: string[] = []

  for (const key of pending) {
    const entry = synced.get(key)
    if (!entry) continue
    sent.set(key, entry.state.value)
    if (entry.state.value === entry.fallback) resets.push(key)
    else values[key] = entry.state.value
  }

  sending = true
  // Re-arm the debounce only after a settled batch: a queue left over after a network failure
  // waits for the person's next move or the next startup, rather than hammering the same downed
  // backend every half second.
  let queueMoved = false
  try {
    if (Object.keys(values).length > 0) await saveSettings(values)
    if (resets.length > 0) await resetSettings(resets)
    // Drop from the queue only what was sent in this exact form: otherwise a setting changed again
    // while the request was in flight would stay in the cache and never reach the database.
    const settled = [...sent]
      .filter(([key, value]) => synced.get(key)?.state.value === value)
      .map(([key]) => key)
    dropFromQueue(settled)
    failures = 0
    queueMoved = true
  } catch (error) {
    const refused = rejectedKeys(error)
    if (refused.length === 0) failed()
    else {
      dropFromQueue(refused)
      queueMoved = true
    }
  } finally {
    sending = false
    // While the request was in flight the debounce may have fired idle — the change it missed
    // would otherwise wait for the person's next move or a page reload.
    if (queueMoved && pending.size > 0) schedule()
  }
}

/** Keys the server called invalid (422 with a field map); empty — the failure isn't about them. */
function rejectedKeys(error: unknown): string[] {
  if (!(error instanceof ApiError) || error.status !== 422) return []
  return Object.keys(error.fields ?? {}).filter((key) => pending.has(key))
}

function dropFromQueue(keys: string[]): void {
  for (const key of keys) pending.delete(key)
  writePending(keys)
}

function failed(): void {
  failures += 1
  if (failures < FAILURES_BEFORE_TOAST) return
  failures = 0
  pushToast(i18n.global.t('settings.interface.sync.failed'), 'warn')
}

/**
 * Start syncing: send what wasn't sent, fetch the values along with the schema, and on the first
 * run carry over what accumulated in the browser.
 *
 * Order matters: the queue first (otherwise the database's answer would roll back a change made on
 * the previous visit that never arrived), then the read.
 */
export async function startSettingsSync(): Promise<void> {
  if (typeof window !== 'undefined') {
    // Leaving the page must not cost the last change: the debounce doesn't get to fire,
    // and `visibilitychange` is the only event the browser delivers reliably.
    document.addEventListener('visibilitychange', () => {
      if (document.visibilityState === 'hidden') void flush()
    })
    window.addEventListener('pagehide', () => void flush())
  }

  await flush()

  const payload = await fetchSettings(true).catch(() => null)
  if (payload === null) return

  applyExternal(payload.values)
  settingsSchema.value = payload.schema ?? []
  await importLegacyKeys(payload.values)
}

/** Database values into refs. Keys whose change hasn't arrived yet are left alone — else a visible rollback. */
function applyExternal(values: Record<string, SettingValue>): void {
  applyingExternal = true
  try {
    for (const [key, value] of Object.entries(values)) {
      const entry = synced.get(key)
      if (!entry || pending.has(key)) continue
      if (entry.state.value !== value) entry.state.value = value
    }
  } finally {
    applyingExternal = false
  }
}

/**
 * One-time carry-over of settings accumulated in the browser before the module existed.
 *
 * Runs only after a successful response: the marker and the removal of old keys with the backend
 * unavailable would erase the person's choice. A key the database already has its own opinion on
 * is left alone — that's a setting made in another browser, and it is newer than our legacy.
 */
async function importLegacyKeys(serverValues: Record<string, SettingValue>): Promise<void> {
  if (typeof localStorage === 'undefined' || localStorage.getItem(IMPORT_MARKER) !== null) return

  const carried: Record<string, SettingValue> = {}
  for (const [legacyKey, key] of Object.entries(LEGACY_KEYS)) {
    const raw = localStorage.getItem(legacyKey)
    const entry = synced.get(key)
    if (raw === null || entry === undefined) continue
    const value = (entry.codec as unknown as Codec<SettingValue>).parse(raw)
    const untouchedOnServer = serverValues[key] === entry.fallback
    if (value !== entry.fallback && untouchedOnServer) carried[key] = value
  }

  try {
    if (Object.keys(carried).length > 0) applyExternal((await saveSettings(carried)).values)
  } catch {
    return
  }

  localStorage.setItem(IMPORT_MARKER, '1')
  for (const legacyKey of Object.keys(LEGACY_KEYS)) localStorage.removeItem(legacyKey)
}

function pendingFromCache(): string[] {
  if (typeof localStorage === 'undefined') return []
  const raw = localStorage.getItem(PENDING_KEY)
  if (raw === null) return []
  try {
    const parsed: unknown = JSON.parse(raw)
    return Array.isArray(parsed) ? parsed.filter((key): key is string => typeof key === 'string') : []
  } catch {
    return []
  }
}

// The queue lives in the same cache: a tab closed within the debounce and a downed backend don't
// lose the change — it is sent on the next open.
//
// Writes merge rather than replace: storage is shared by all tabs, and a tab writing its whole set
// there would erase a neighbour's unsent changes. Only what is named explicitly — what this tab
// settled — leaves the queue.
function writePending(settled: string[] = []): void {
  if (typeof localStorage === 'undefined') return
  const queued = new Set([...pendingFromCache(), ...pending])
  for (const key of settled) queued.delete(key)
  if (queued.size === 0) localStorage.removeItem(PENDING_KEY)
  else localStorage.setItem(PENDING_KEY, JSON.stringify([...queued]))
}
