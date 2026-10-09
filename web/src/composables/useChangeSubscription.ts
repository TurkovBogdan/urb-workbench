import { getCurrentInstance, onActivated, onBeforeUnmount, onDeactivated, onMounted } from 'vue'

import { useChangesStore, type Change } from '@/stores/changes'

// A screen's subscription to the change feed — tied to the lifetime of that screen.
//
// Everything that tends to break in such a subscription is gathered here, not in every screen. The
// subscription has three states, and at any moment it is in exactly one:
//
// - VISIBLE (mounted or back from `KeepAlive`) — its changes accumulate for `BATCH_MS` after the
//   last one and go to `onChange` as one batch: the agent makes five calls in a row — the screen
//   reloads once; a feed reconnect — `onResync`;
// - HIDDEN (the page is alive in `KeepAlive` but not on screen) — its changes are not processed,
//   only noted; on return — a single reload (`onResync`), and only if something happened. A page
//   that reloads itself on return (`reloadsOnReturn`) does not get a second one: two identical
//   requests in a row add nothing;
// - DISPOSED (unmounted) — not a single handler is left in the store.
//
// A state change first removes all handlers of the previous state, then installs the new ones: a
// "hidden watcher" cannot leak into the visible state, nor a handler beyond the screen's lifetime.
// The echo of our own edits never reaches here at all — the store filters it out
// (`stores/changes.ts`).

/** How long to wait for quiet after a change before handing the batch to the screen. */
const BATCH_MS = 250

export interface ChangeSubscription {
  /** Which entities to listen to (`tasks.task`, `tasks.stage`, …). */
  entities: string[]
  /** Is this change about me? Called for every change of the listened entities. */
  match: (change: Change) => boolean
  /** A batch of its own changes — after `BATCH_MS` of quiet. */
  onChange: (changes: Change[]) => void
  /** Reload everything: a feed reconnect or the screen returning after missing something. */
  onResync: () => void
  /** The screen reloads itself in `onActivated` — that covers whatever it missed while hidden. */
  reloadsOnReturn?: boolean
}

type State = 'visible' | 'hidden' | 'disposed'

export function useChangeSubscription(spec: ChangeSubscription): void {
  if (!getCurrentInstance()) {
    throw new Error('useChangeSubscription must be called from a component setup')
  }
  const changes = useChangesStore()

  let state: State | null = null
  let missed = false
  let offs: Array<() => void> = []
  let batch: Change[] = []
  let timer: ReturnType<typeof setTimeout> | undefined

  function unsubscribe(): void {
    for (const off of offs) off()
    offs = []
  }

  function flush(): void {
    timer = undefined
    const pending = batch
    batch = []
    if (pending.length) spec.onChange(pending)
  }

  function dropBatch(): boolean {
    const had = batch.length > 0
    clearTimeout(timer)
    timer = undefined
    batch = []
    return had
  }

  function show(): void {
    if (state === 'visible' || state === 'disposed') return
    unsubscribe()
    state = 'visible'
    offs = [
      ...spec.entities.map((entity) =>
        changes.on(entity, (change) => {
          if (!spec.match(change)) return
          batch.push(change)
          clearTimeout(timer)
          timer = setTimeout(flush, BATCH_MS)
        }),
      ),
      changes.onResync(() => spec.onResync()),
    ]
    if (missed) {
      missed = false
      if (!spec.reloadsOnReturn) spec.onResync()
    }
  }

  function hide(): void {
    if (state !== 'visible') return
    unsubscribe()
    state = 'hidden'
    // An undelivered batch is not lost: the screen will reload when it returns.
    if (dropBatch()) missed = true
    offs = [
      ...spec.entities.map((entity) =>
        changes.on(entity, (change) => {
          if (spec.match(change)) missed = true
        }),
      ),
      changes.onResync(() => { missed = true }),
    ]
  }

  function dispose(): void {
    unsubscribe()
    dropBatch()
    state = 'disposed'
  }

  // A page in `KeepAlive` fires both hooks on first show; `show` ignores the repeat.
  onMounted(show)
  onActivated(show)
  onDeactivated(hide)
  onBeforeUnmount(dispose)
}
