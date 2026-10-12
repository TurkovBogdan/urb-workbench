import { shallowReactive } from 'vue'
import { defineStore } from 'pinia'

import { fetchPreviews, PREVIEW_BATCH_MAX, type PreviewRecord } from '@/api/lookup'
import { ANY_ENTITY, useChangesStore, type Change } from '@/stores/changes'

// Previews of entity codes — the frontend half of `core_lookup`: what a code quoted in a body
// stands for (title, description, page), or why there is nothing to show.
//
// It sits in the foundation (`stores/`): the pill that reads it lives in `components/markdown`,
// and the foundation does not import `features/*`. It knows nothing about entity types or
// workspaces — the workspace feature tells it which workspace to narrow by (`setWorkspace`).
//
// The map only grows: a body asks for its codes once it is drawn (`ensure`), and only the codes the
// map does not hold yet go to the network, collected over one tick into one request. A miss is a
// record too — otherwise a code that does not exist would be asked for on every render.
//
// Kept fresh by the change feed, own edits included (the tab's rename of a task must reach the
// pill of that task in another panel):
// - a change naming codes the map holds re-asks those codes;
// - a deletion, a codex mount, a change without codes and a reconnect re-ask the whole map — a
//   preview may hang on another entity (a stage is "deleted" with its task, a codex note is
//   visible through its codex's mount), and the event names only that other one. Such events are
//   rare and the map is small, so one request for all of it is cheaper than tracking who hangs on
//   whom;
// - switching the workspace drops the map: "belongs to another workspace" is true only for the
//   workspace it was asked under.
// A code re-asked while its request is in flight is asked again when that answer lands: the answer
// may describe the entity before the change.

/** Entities whose change can alter the preview of codes it does not name. */
const WIDE_ENTITIES = new Set(['codex.mount'])

function failed(code: string): PreviewRecord {
  return {
    code,
    title: '',
    description: '',
    link: '',
    error: { code: 'failed', message: 'The preview could not be loaded.' },
  }
}

export const usePreviewStore = defineStore('preview', () => {
  const records = shallowReactive(new Map<string, PreviewRecord>())

  let workspace: string | null = null
  // Bumped by a workspace switch: an answer asked under the previous workspace is dropped.
  let generation = 0
  const queued = new Set<string>()
  const inflight = new Set<string>()
  // Re-asked while in flight: asked once more when the answer lands.
  const stale = new Set<string>()
  let scheduled = false

  /** The record of a code — `undefined` while it has not arrived. Reactive per code. */
  function get(code: string): PreviewRecord | undefined {
    return records.get(code)
  }

  /** Make sure these codes are loaded: the ones the map lacks go out in the next request. */
  function ensure(codes: Iterable<string>): void {
    for (const code of codes) {
      if (!records.has(code) && !inflight.has(code)) queued.add(code)
    }
    schedule()
  }

  /** Ask these codes again, keeping what is shown until the answer arrives. */
  function refresh(codes: Iterable<string>): void {
    for (const code of codes) {
      if (inflight.has(code)) stale.add(code)
      else queued.add(code)
    }
    schedule()
  }

  /** Ask every code the map holds again — the manual "refresh everything". */
  function refreshAll(): void {
    refresh([...records.keys(), ...inflight])
  }

  /** The workspace previews are narrowed by (`WORKSPACE@…`); a switch drops the map and re-asks it. */
  function setWorkspace(code: string | null): void {
    if (code === workspace) return
    workspace = code
    generation += 1
    const known = [...records.keys(), ...inflight, ...queued]
    records.clear()
    inflight.clear()
    stale.clear()
    queued.clear()
    ensure(known)
  }

  function schedule(): void {
    if (scheduled || !queued.size) return
    scheduled = true
    queueMicrotask(flush)
  }

  function flush(): void {
    scheduled = false
    const codes = [...queued]
    queued.clear()
    for (let start = 0; start < codes.length; start += PREVIEW_BATCH_MAX) {
      void load(codes.slice(start, start + PREVIEW_BATCH_MAX))
    }
  }

  async function load(codes: string[]): Promise<void> {
    const asked = generation
    for (const code of codes) inflight.add(code)
    let answer: PreviewRecord[] = []
    try {
      answer = await fetchPreviews(codes, workspace)
    } catch {
      // A failed request leaves a `failed` record: the next reconnect re-asks the whole map.
    }
    if (asked !== generation) return
    const byCode = new Map(answer.map((record) => [record.code, record]))
    for (const code of codes) {
      inflight.delete(code)
      records.set(code, Object.freeze(byCode.get(code) ?? failed(code)))
      if (stale.delete(code)) queued.add(code)
    }
    schedule()
  }

  function onChange(change: Change): void {
    if (change.event === 'deleted' || !change.ids.length || WIDE_ENTITIES.has(change.entity)) {
      refreshAll()
      return
    }
    refresh(change.ids.filter((code) => records.has(code) || inflight.has(code)))
  }

  const changes = useChangesStore()
  changes.on(ANY_ENTITY, onChange, { own: true })
  changes.onResync(refreshAll)

  return { get, ensure, refresh, refreshAll, setWorkspace }
})
