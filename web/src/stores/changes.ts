import { ref } from 'vue'
import { defineStore } from 'pinia'

import { CLIENT_ID } from '@/api/client/client-id'

// The data change feed — the frontend half of the `core_changes` module.
//
// It sits in the foundation (`stores/`), not as a module in `features/`: different modules
// subscribe to it (tasks, groups, others later), and a module cannot import a module
// (`tests/apps/test_web_layer_boundaries.py`). It doesn't know about entities — it has nothing to
// know.
//
// The ECHO OF OUR OWN EDITS is not handed to subscribers. Every message carries `origin` — the id
// of the tab whose request caused it (`api/client/client-id.ts`). The screen has already accounted
// for its own save from the request's response, and the event about it arrives BEFORE that
// response (the backend sends it right after the commit): hand it to a subscriber and the task
// page would see "the field changed in the database while I have it edited" and raise a false
// conflict on its own edit. The corner indicator does show our own — it is about "what was
// updated", not "what to reload".
//
// One connection for the whole app: a WebSocket the backend sends into which declared entities
// were created, updated or deleted. WebSocket and not SSE because an SSE stream holds one of the
// six HTTP connections a browser allows per origin — a few open tabs starved every request. The
// store itself knows nothing about entities — it receives messages and hands them to whoever
// subscribed to the entity (`on`). What to do with a change — reload a list, a card, nothing — is
// up to the subscriber.
//
// Unlike `EventSource`, a socket does not come back by itself: a drop is repaired here, after a
// pause that doubles with every failed attempt. A link that died silently (a laptop back from
// sleep) is caught by the watchdog: the backend pings at the interval named in `hello`, and a
// silence of several intervals means the socket is replaced. A handshake nobody answers is cut by
// the `hello` deadline the same way.
//
// What was missed during a drop is not resent: the backend stores nothing. So every REconnect (and
// a `resync` frame when the tab fell behind) is handed to `onResync` subscribers — "reload what's
// on your screen"; the first connect is not: the screens have just loaded anyway.

/** What happened to an entity. The names are a contract with the backend (`core_changes/capture.py`). */
export type ChangeEvent = 'created' | 'updated' | 'deleted'

/**
 * One change: the entity, the event, the codes of the affected items and the codes of what they
 * belong to.
 *
 * Empty `ids` — a bulk operation without named codes: the subscriber reloads everything it has.
 * `refs` — by them a screen understands "this is about me" without knowing which entity arrived
 * (for a stage it holds its task).
 */
export interface Change {
  entity: string
  event: ChangeEvent
  ids: string[]
  refs: string[]
  /** The edit was made by this same tab. Subscribers don't get these; the indicator does. */
  own: boolean
}

/** A feed message: one backend transaction. `origin` — the source tab's id or `null`. */
interface ChangesMessage {
  origin: string | null
  changes: Omit<Change, 'own'>[]
}

export type ChangeHandler = (change: Change) => void

/** A feed occurrence: a change or — with `change: null` — "reload everything" (reconnect, lag). */
export interface ChangeSignal {
  seq: number
  change: Change | null
}

/** A subscription to all entities at once — for debugging and logging, not for screens. */
export const ANY_ENTITY = '*'

/** A frame of the feed socket. The shape is a contract with the backend (`core_changes/api.py`). */
type Frame =
  | { event: 'hello'; ping: number }
  | { event: 'changes'; data: ChangesMessage }
  | { event: 'resync' }
  | { event: 'ping' }

const FEED_PATH = '/internal/core/changes/ws'

/** The first pause before reconnecting; every failed attempt doubles it, up to the ceiling. */
const RECONNECT_MIN_MS = 1000
const RECONNECT_MAX_MS = 15000

/** How many ping intervals of silence mean the link is dead rather than quiet. */
const SILENT_PINGS = 2.5

/**
 * How long a new socket may go without `hello`. The browser itself never gives up on a handshake
 * nobody answers (a frozen backend process: the kernel accepts the connection, nobody replies) —
 * without this deadline the feed would hang in "connecting" for good.
 */
const HELLO_TIMEOUT_MS = 10000

function feedUrl(): string {
  const scheme = location.protocol === 'https:' ? 'wss:' : 'ws:'
  return `${scheme}//${location.host}${FEED_PATH}`
}

/** How many recent changes to keep for display; for the feed this is history at a glance, not a log. */
const RECENT_LIMIT = 50

export const useChangesStore = defineStore('changes', () => {
  const connected = ref(false)
  const recent = ref<Change[]>([])
  // The feed's latest occurrence — for the corner indicator (`ChangesIndicator`). `seq` grows on
  // each one: two identical changes in a row are two occurrences, and the second must show too.
  const latest = ref<ChangeSignal | null>(null)
  let seq = 0

  const handlers = new Map<string, Set<ChangeHandler>>()
  const resyncHandlers = new Set<() => void>()

  // `wanted` — the app asked for the feed and has not let it go: a drop is repaired only then.
  let wanted = false
  let socket: WebSocket | null = null
  let everConnected = false
  let attempt = 0
  let reconnectTimer: ReturnType<typeof setTimeout> | undefined
  let watchdogTimer: ReturnType<typeof setInterval> | undefined
  let helloTimer: ReturnType<typeof setTimeout> | undefined
  let lastFrameAt = 0

  /** Open the connection. A repeat call does nothing: there is one feed per app. */
  function connect(): void {
    if (wanted) return
    wanted = true
    open()
  }

  function disconnect(): void {
    wanted = false
    clearTimeout(reconnectTimer)
    drop()
  }

  function open(): void {
    const ws = new WebSocket(feedUrl())
    socket = ws
    // A replaced socket may still deliver its last events; only the current one is listened to.
    ws.onmessage = (event: MessageEvent<string>) => {
      if (socket !== ws) return
      lastFrameAt = Date.now()
      receive(JSON.parse(event.data) as Frame)
    }
    // `error` is always followed by `close`, so the drop is handled once, here.
    ws.onclose = () => {
      if (socket !== ws) return
      drop()
      scheduleReconnect()
    }
    helloTimer = setTimeout(() => {
      if (socket !== ws) return
      drop()
      scheduleReconnect()
    }, HELLO_TIMEOUT_MS)
  }

  function receive(frame: Frame): void {
    switch (frame.event) {
      case 'hello':
        // Connected is `hello`, not `open`: a backend that accepts and closes at once (degraded,
        // schema behind the code) must not count as a reconnect and set screens reloading.
        clearTimeout(helloTimer)
        connected.value = true
        attempt = 0
        armWatchdog(frame.ping * 1000)
        // A reconnect, not the first open: something may have changed while we were away.
        if (everConnected) resync()
        everConnected = true
        break
      case 'changes': {
        const own = frame.data.origin !== null && frame.data.origin === CLIENT_ID
        for (const change of frame.data.changes) dispatch({ ...change, own })
        break
      }
      case 'resync':
        resync()
        break
      case 'ping':
        break
    }
  }

  function drop(): void {
    clearTimeout(helloTimer)
    clearInterval(watchdogTimer)
    const ws = socket
    socket = null
    ws?.close()
    connected.value = false
  }

  function scheduleReconnect(): void {
    if (!wanted) return
    // Jittered, so that tabs dropped by one backend restart do not all knock at the same moment.
    const pause = Math.min(RECONNECT_MAX_MS, RECONNECT_MIN_MS * 2 ** attempt)
    attempt += 1
    reconnectTimer = setTimeout(open, pause * (0.5 + Math.random() / 2))
  }

  function armWatchdog(pingMs: number): void {
    clearInterval(watchdogTimer)
    watchdogTimer = setInterval(() => {
      if (Date.now() - lastFrameAt < pingMs * SILENT_PINGS) return
      drop()
      scheduleReconnect()
    }, pingMs)
  }

  function dispatch(change: Change): void {
    recent.value = [change, ...recent.value].slice(0, RECENT_LIMIT)
    latest.value = { seq: ++seq, change }
    if (change.own) return
    for (const key of [change.entity, ANY_ENTITY]) {
      for (const handler of handlers.get(key) ?? []) handler(change)
    }
  }

  function resync(): void {
    latest.value = { seq: ++seq, change: null }
    for (const handler of resyncHandlers) handler()
  }

  /**
   * Subscribe to changes of an entity (`tasks.task`) or of all at once (`ANY_ENTITY`). Returns the
   * unsubscribe — call it when the subscriber unmounts, otherwise the handler outlives its screen.
   */
  function on(entity: string, handler: ChangeHandler): () => void {
    let bucket = handlers.get(entity)
    if (!bucket) handlers.set(entity, (bucket = new Set()))
    bucket.add(handler)
    return () => bucket.delete(handler)
  }

  /** Subscribe to "reload everything": a reconnect after a drop, and the tab falling behind. */
  function onResync(handler: () => void): () => void {
    resyncHandlers.add(handler)
    return () => resyncHandlers.delete(handler)
  }

  /** How many handlers are subscribed now — to verify that screens unsubscribe. */
  function subscriberCount(): number {
    let total = resyncHandlers.size
    for (const bucket of handlers.values()) total += bucket.size
    return total
  }

  return { connected, recent, latest, connect, disconnect, on, onResync, subscriberCount }
})
