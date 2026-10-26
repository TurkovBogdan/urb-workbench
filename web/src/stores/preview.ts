import {
  computed, inject, onScopeDispose, provide, ref, shallowReactive, toValue, watch,
  type ComputedRef, type InjectionKey, type MaybeRefOrGetter,
} from 'vue'
import { defineStore } from 'pinia'

import { fetchPreviews, PREVIEW_BATCH_MAX, type PreviewRecord } from '@/api/lookup'
import { ANY_ENTITY, useChangesStore, type Change } from '@/stores/changes'

// Previews of entity codes — the frontend half of `core_lookup`: what a code quoted in a body
// stands for (title, description, page), or why there is nothing to show.
//
// It sits in the foundation (`stores/`): the pill that reads it lives in `components/markdown`,
// and the foundation does not import `features/*`. It knows nothing about entity types or
// workspaces — the workspace feature tells it which workspace the person works in
// (`setWorkspace`), and a page showing an entity of its own workspace says so to everything drawn
// under it (`providePreviewWorkspace`, read through `usePreviews`).
//
// "Belongs to another workspace" is true only for the workspace a code was asked under, so the map
// is one per workspace asked (and per page entity, which names files its own way): a code shown
// under two workspaces has two records, and an answer is written only into the map it was asked
// for.
//
// A map only grows: a body asks for its codes once it is drawn (`ensure`), and only the codes the
// map does not hold yet go to the network, collected over one tick into one request per workspace.
// A miss is a record too — otherwise a code that does not exist would be asked for on every render.
//
// Kept fresh by the change feed, own edits included (the tab's rename of a task must reach the
// pill of that task in another panel):
// - a change naming codes the map holds re-asks those codes;
// - a deletion, a codex mount, a change without codes and a reconnect re-ask the whole map — a
//   preview may hang on another entity (a stage is "deleted" with its task, a codex note is
//   visible through its codex's mount), and the event names only that other one. Such events are
//   rare and the map is small, so one request for all of it is cheaper than tracking who hangs on
//   whom;
// - switching the selected workspace asks its codes under the new one and drops the old map, unless
//   a page still shows its own workspace through it; a page's map goes with its last pill.
// A code re-asked while its request is in flight is asked again when that answer lands: the answer
// may describe the entity before the change.

/** Entities whose change can alter the preview of codes it does not name. */
const WIDE_ENTITIES = new Set(['codex.mount'])

/**
 * The previews asked under one workspace (`null` — not narrowed) and, on an entity's page, for
 * that entity (`holder`): a file is named as the page's own entity names it.
 */
interface Scope {
  workspace: string | null
  holder: string | null
  records: Map<string, PreviewRecord>
  queued: Set<string>
  inflight: Set<string>
  // Re-asked while in flight: asked once more when the answer lands.
  stale: Set<string>
  // Pages holding this workspace open (`usePreviews` under `providePreviewWorkspace`).
  users: number
}

const keyOf = (workspace: string | null, holder: string | null = null): string =>
  `${workspace ?? ''}|${holder ?? ''}`

const hashOf = (code: string): string => (code.split('@')[1] ?? code).toUpperCase()

function failed(code: string): PreviewRecord {
  return {
    code,
    title: '',
    description: '',
    link: '',
    mime: '',
    held: false,
    error: { code: 'failed', message: 'The preview could not be loaded.' },
  }
}

export const usePreviewStore = defineStore('preview', () => {
  // Plain, not reactive: a component reads a scope's `records`, which are, and a scope made while
  // a render reads it must not count as a change of what that render depends on.
  const scopes = new Map<string, Scope>()
  // The workspace selected in the sidebar — what a code is asked under when no page says otherwise.
  const selected = ref<string | null>(null)
  let scheduled = false

  function scopeOf(workspace: string | null, holder: string | null = null): Scope {
    const key = keyOf(workspace, holder)
    let scope = scopes.get(key)
    if (!scope) {
      scope = {
        workspace,
        holder,
        records: shallowReactive(new Map<string, PreviewRecord>()),
        queued: new Set(),
        inflight: new Set(),
        stale: new Set(),
        users: 0,
      }
      scopes.set(key, scope)
    }
    return scope
  }

  // `undefined` — the selected workspace; `null` — not narrowed at all.
  const under = (workspace: string | null | undefined): string | null =>
    workspace === undefined ? selected.value : workspace

  /**
   * The record of a code under a workspace (and a page's entity) — `undefined` while it has not
   * arrived. Reactive per code, and to the selected workspace when none is named.
   */
  function get(code: string, workspace?: string | null, holder?: string | null): PreviewRecord | undefined {
    return scopeOf(under(workspace), holder ?? null).records.get(code)
  }

  /** Make sure these codes are loaded: the ones the map lacks go out in the next request. */
  function ensure(codes: Iterable<string>, workspace?: string | null, holder?: string | null): void {
    const scope = scopeOf(under(workspace), holder ?? null)
    for (const code of codes) {
      if (!scope.records.has(code) && !scope.inflight.has(code)) scope.queued.add(code)
    }
    schedule()
  }

  function refreshIn(scope: Scope, codes: Iterable<string>): void {
    for (const code of codes) {
      if (scope.inflight.has(code)) scope.stale.add(code)
      else scope.queued.add(code)
    }
  }

  /**
   * Ask these codes again wherever they are held, keeping what is shown until the answer arrives.
   * A code is matched by its hash, whatever word it is quoted under: one stored file is both
   * `FILE@` and `IMAGE@`, and the feed names it by one of them only.
   */
  function refresh(codes: Iterable<string>): void {
    const hashes = new Set([...codes].map(hashOf))
    for (const scope of scopes.values()) {
      refreshIn(scope, [...scope.records.keys(), ...scope.inflight].filter((code) => hashes.has(hashOf(code))))
    }
    schedule()
  }

  /** Ask every code every map holds again — the manual "refresh everything". */
  function refreshAll(): void {
    for (const scope of scopes.values()) refreshIn(scope, [...scope.records.keys(), ...scope.inflight])
    schedule()
  }

  const own = (scope: Scope): boolean => scopes.get(keyOf(scope.workspace, scope.holder)) === scope

  function drop(scope: Scope): void {
    if (own(scope)) scopes.delete(keyOf(scope.workspace, scope.holder))
  }

  /** The workspace selected in the sidebar (`WORKSPACE@…`); a switch asks its codes under the new one. */
  function setWorkspace(code: string | null): void {
    if (code === selected.value) return
    const previous = scopes.get(keyOf(selected.value))
    selected.value = code
    if (!previous) return
    const known = [...previous.records.keys(), ...previous.inflight, ...previous.queued]
    if (!previous.users) drop(previous)
    ensure(known)
  }

  /** A page shows codes under `workspace` (for `holder`): its map stays while the page does. */
  function retain(workspace: string | null, holder: string | null = null): void {
    scopeOf(workspace, holder).users += 1
  }

  function release(workspace: string | null, holder: string | null = null): void {
    const scope = scopes.get(keyOf(workspace, holder))
    if (!scope) return
    scope.users -= 1
    if (scope.users <= 0 && keyOf(workspace, holder) !== keyOf(selected.value)) drop(scope)
  }

  function schedule(): void {
    if (scheduled) return
    scheduled = true
    queueMicrotask(flush)
  }

  function flush(): void {
    scheduled = false
    for (const scope of scopes.values()) {
      const codes = [...scope.queued]
      scope.queued.clear()
      for (let start = 0; start < codes.length; start += PREVIEW_BATCH_MAX) {
        void load(scope, codes.slice(start, start + PREVIEW_BATCH_MAX))
      }
    }
  }

  async function load(scope: Scope, codes: string[]): Promise<void> {
    for (const code of codes) scope.inflight.add(code)
    let answer: PreviewRecord[] = []
    try {
      answer = await fetchPreviews(codes, scope.workspace, scope.holder)
    } catch {
      // A failed request leaves a `failed` record: the next reconnect re-asks the whole map.
    }
    // The map was dropped meanwhile (the workspace switched away, its page closed).
    if (!own(scope)) return
    const byCode = new Map(answer.map((record) => [record.code, record]))
    for (const code of codes) {
      scope.inflight.delete(code)
      scope.records.set(code, Object.freeze(byCode.get(code) ?? failed(code)))
      if (scope.stale.delete(code)) scope.queued.add(code)
    }
    schedule()
  }

  function onChange(change: Change): void {
    if (change.event === 'deleted' || !change.ids.length || WIDE_ENTITIES.has(change.entity)) {
      refreshAll()
      return
    }
    refresh(change.ids)
  }

  const changes = useChangesStore()
  changes.on(ANY_ENTITY, onChange, { own: true })
  changes.onResync(refreshAll)

  return { get, ensure, refresh, refreshAll, setWorkspace, retain, release }
})

// The workspace of the entity a page shows, for every code drawn under it, and the entity itself.
// A task opened by a link from another workspace is read in its own: under the sidebar's choice
// all of its codes would be "of another workspace". The entity names a file as its own files panel
// does — the same file may carry another title at another task of the workspace.
interface PageScope {
  workspace: string
  holder: string | null
}

const PREVIEW_PAGE: InjectionKey<ComputedRef<PageScope | undefined>> = Symbol('preview-page')

/**
 * Show the previews under this page in `workspace` (`WORKSPACE@…`) and for `holder` (`TASK@…`,
 * `CODEX@…`). No workspace yet — the selected one, and no holder either.
 */
export function providePreviewWorkspace(
  workspace: MaybeRefOrGetter<string | null | undefined>,
  holder?: MaybeRefOrGetter<string | null | undefined>,
): void {
  provide(PREVIEW_PAGE, computed(() => {
    const named = toValue(workspace)
    return named ? { workspace: named, holder: toValue(holder) || null } : undefined
  }))
}

/**
 * The previews as a component under a page sees them: in the page's workspace and for its entity
 * when it names them (`providePreviewWorkspace`), otherwise in the selected workspace. The codes it
 * asked are asked again when the page's scope arrives or changes.
 */
export function usePreviews(): {
  get: (code: string) => PreviewRecord | undefined
  ensure: (codes: Iterable<string>) => void
} {
  const store = usePreviewStore()
  const page = inject(PREVIEW_PAGE, null)
  const asked = new Set<string>()
  // The page scope this component keeps open in the store.
  let held: PageScope | undefined
  if (page) {
    // By value: the computed hands out a new object on every change of what it reads.
    watch(() => (page.value ? keyOf(page.value.workspace, page.value.holder) : ''), () => {
      const now = page.value
      if (now) store.retain(now.workspace, now.holder)
      if (held) store.release(held.workspace, held.holder)
      held = now
      store.ensure(asked, now?.workspace, now?.holder)
    }, { immediate: true })
    onScopeDispose(() => {
      if (held) store.release(held.workspace, held.holder)
    })
  }
  return {
    get: (code) => store.get(code, page?.value?.workspace, page?.value?.holder),
    ensure: (codes) => {
      const list = [...codes]
      for (const code of list) asked.add(code)
      store.ensure(list, page?.value?.workspace, page?.value?.holder)
    },
  }
}
