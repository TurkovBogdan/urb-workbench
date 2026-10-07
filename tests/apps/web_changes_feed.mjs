// Scenarios for the change feed store (`web/src/stores/changes.ts`), executed under Node against
// the real file — see `test_web_changes_feed.py`. Run as `node … web_changes_feed.mjs <scenario>`;
// a failed `assert` exits non-zero with the reason on stderr.
//
// The browser is replaced by three fakes: a `WebSocket` the scenario drives from the backend's
// side, a clock whose time moves only by `advance`, and a `location`. Everything else — Vue, Pinia,
// the store, the tab id — is the real code.

import assert from 'node:assert/strict'
import { register } from 'node:module'

const WEB_SRC = new URL('../../web/src/', import.meta.url)

// `@/…` is the Vite alias for `web/src/…`; bare packages resolve from `web/`, where node_modules
// lives — the harness and the store must share one Vue and one Pinia.
register(
  'data:text/javascript,' +
    encodeURIComponent(`
      const WEB_SRC = ${JSON.stringify(WEB_SRC.href)}
      const HARNESS = ${JSON.stringify(import.meta.url)}
      export async function resolve(specifier, context, next) {
        if (specifier.startsWith('@/')) return next(WEB_SRC + specifier.slice(2) + '.ts', context)
        if (context.parentURL === HARNESS && /^[a-z]/.test(specifier) && !specifier.startsWith('node:')) {
          return next(specifier, { ...context, parentURL: WEB_SRC + 'main.ts' })
        }
        return next(specifier, context)
      }
    `),
)

// ── the clock ────────────────────────────────────────────────────────────────
let now = 1_000_000
let nextTimerId = 1
const timers = new Map()

globalThis.setTimeout = (fn, ms) => {
  const id = nextTimerId++
  timers.set(id, { at: now + ms, fn, every: null })
  return id
}
globalThis.setInterval = (fn, ms) => {
  const id = nextTimerId++
  timers.set(id, { at: now + ms, fn, every: ms })
  return id
}
globalThis.clearTimeout = (id) => timers.delete(id)
globalThis.clearInterval = (id) => timers.delete(id)
Date.now = () => now
// The jitter takes the whole pause: the schedule becomes exact and checkable.
Math.random = () => 1

function advance(ms) {
  const end = now + ms
  for (;;) {
    let due = null
    for (const [id, timer] of timers) {
      if (timer.at <= end && (!due || timer.at < due[1].at)) due = [id, timer]
    }
    if (!due) break
    const [id, timer] = due
    now = timer.at
    if (timer.every === null) timers.delete(id)
    else timer.at += timer.every
    timer.fn()
  }
  now = end
}

// ── the socket ───────────────────────────────────────────────────────────────
const sockets = []

class FakeSocket {
  constructor(url) {
    this.url = url
    this.closedByClient = false
    this.onmessage = null
    this.onclose = null
    sockets.push(this)
  }

  // The store closing it. A real browser reports `close` later, asynchronously; reporting it at
  // once is the harsher case for the store, which must ignore a socket it has already let go.
  close() {
    this.closedByClient = true
    this.onclose?.({ code: 1005 })
  }

  send(frame) {
    this.onmessage?.({ data: JSON.stringify(frame) })
  }

  hello(ping = 15) {
    this.send({ event: 'hello', ping })
  }

  lost(code = 1006) {
    this.onclose?.({ code })
  }
}

globalThis.WebSocket = FakeSocket
globalThis.location = { protocol: process.env.FEED_PROTOCOL ?? 'http:', host: 'wb.test' }

const { createPinia, setActivePinia } = await import('pinia')
setActivePinia(createPinia())
const { useChangesStore, ANY_ENTITY } = await import('@/stores/changes')
const { CLIENT_ID } = await import('@/api/client/client-id')

const store = useChangesStore()
const received = []
const resyncs = []
store.on('tasks.task', (change) => received.push(change))
store.onResync(() => resyncs.push(now))

const last = () => sockets.at(-1)

/** How long until the store's next timer fires — the pause it has scheduled. */
function nextTimerIn() {
  const ats = [...timers.values()].map((timer) => timer.at)
  return ats.length ? Math.min(...ats) - now : null
}

function changes(origin, ...ids) {
  return { event: 'changes', data: { origin, changes: [{ entity: 'tasks.task', event: 'updated', ids, refs: [] }] } }
}

/** Fail the current socket before `hello` and move to the next attempt; returns the pause. */
function failAttempt() {
  last().lost()
  const pause = nextTimerIn()
  const before = sockets.length
  advance(pause)
  assert.equal(sockets.length, before + 1, 'the pause ends in a new attempt')
  return pause
}

// ── scenarios ────────────────────────────────────────────────────────────────
const scenarios = {
  opens_one_socket_on_the_feed_path() {
    store.connect()
    store.connect()
    assert.equal(sockets.length, 1)
    const scheme = location.protocol === 'https:' ? 'wss:' : 'ws:'
    assert.equal(last().url, `${scheme}//wb.test/internal/core/changes/ws`)
  },

  first_hello_connects_without_resync() {
    store.connect()
    assert.equal(store.connected, false, 'an open socket is not yet a connection')
    last().hello()
    assert.equal(store.connected, true)
    assert.deepEqual(resyncs, [])
  },

  reconnect_after_a_drop_resyncs_once() {
    store.connect()
    last().hello()
    last().lost()
    assert.equal(store.connected, false)
    advance(999)
    assert.equal(sockets.length, 1, 'no reconnect before the pause')
    advance(1)
    assert.equal(sockets.length, 2)
    assert.deepEqual(resyncs, [], 'the resync waits for hello')
    last().hello()
    assert.equal(store.connected, true)
    assert.equal(resyncs.length, 1)
  },

  changes_reach_subscribers_except_own_echo() {
    const everything = []
    store.on(ANY_ENTITY, (change) => everything.push(change))
    store.connect()
    last().hello()
    last().send(changes('another-tab', 'TASK@1'))
    last().send(changes(null, 'TASK@2'))
    last().send(changes(CLIENT_ID, 'TASK@3'))
    assert.deepEqual(received.map((change) => [change.ids[0], change.own]), [['TASK@1', false], ['TASK@2', false]])
    assert.equal(everything.length, 2, 'the echo reaches no subscriber at all')
    assert.deepEqual(store.recent.map((change) => [change.ids[0], change.own]), [
      ['TASK@3', true],
      ['TASK@2', false],
      ['TASK@1', false],
    ])
  },

  resync_frame_reaches_resync_subscribers() {
    store.connect()
    last().hello()
    last().send({ event: 'resync', data: {} })
    assert.equal(resyncs.length, 1)
    assert.equal(store.latest?.change, null)
  },

  pause_doubles_up_to_the_ceiling() {
    store.connect()
    const pauses = Array.from({ length: 6 }, failAttempt)
    assert.deepEqual(pauses, [1000, 2000, 4000, 8000, 15000, 15000])
  },

  pause_starts_over_after_a_hello() {
    store.connect()
    failAttempt()
    failAttempt()
    last().hello()
    assert.equal(failAttempt(), 1000)
  },

  silent_handshake_is_cut_at_the_hello_deadline() {
    store.connect()
    advance(9999)
    assert.equal(last().closedByClient, false)
    advance(1)
    assert.equal(sockets[0].closedByClient, true, 'a handshake nobody answers is abandoned')
    advance(nextTimerIn())
    assert.equal(sockets.length, 2, 'and a new attempt follows')
  },

  hello_in_time_disarms_the_deadline() {
    store.connect()
    advance(5000)
    last().hello()
    advance(10_000)
    assert.equal(last().closedByClient, false)
    assert.equal(sockets.length, 1)
  },

  pinged_link_is_kept() {
    store.connect()
    last().hello(15)
    for (let i = 0; i < 20; i += 1) {
      advance(15_000)
      last().send({ event: 'ping' })
    }
    assert.equal(sockets.length, 1)
    assert.equal(last().closedByClient, false)
    assert.equal(store.connected, true)
  },

  silent_link_is_replaced_by_the_watchdog() {
    store.connect()
    last().hello(15)
    advance(30_000)
    assert.equal(last().closedByClient, false, 'two pings missed is still quiet, not dead')
    advance(15_000)
    assert.equal(sockets[0].closedByClient, true)
    assert.equal(store.connected, false)
    advance(nextTimerIn())
    assert.equal(sockets.length, 2)
    last().hello(15)
    assert.equal(resyncs.length, 1)
  },

  replaced_socket_is_ignored() {
    store.connect()
    const first = last()
    first.hello(15)
    advance(45_000)
    advance(nextTimerIn())
    assert.equal(sockets.length, 2, 'one drop is one reconnect, however the old socket reports it')
    last().hello(15)
    first.send(changes('another-tab', 'TASK@old'))
    first.lost()
    assert.deepEqual(received, [])
    assert.equal(store.connected, true, 'the old socket does not take the connection down')
    advance(20_000)
    assert.equal(sockets.length, 2, 'the old socket schedules nothing')
  },

  refused_before_hello_is_not_a_reconnect() {
    store.connect()
    last().lost(1013)
    assert.equal(store.connected, false)
    advance(nextTimerIn())
    last().hello()
    assert.deepEqual(resyncs, [], 'the screens never had data from a feed to miss')
  },

  disconnect_stops_reconnecting() {
    store.connect()
    last().hello()
    store.disconnect()
    assert.equal(sockets[0].closedByClient, true)
    assert.equal(store.connected, false)
    advance(120_000)
    assert.equal(sockets.length, 1)
    assert.equal(nextTimerIn(), null, 'no timer is left behind')
  },

  disconnect_before_hello_leaves_no_timer() {
    store.connect()
    store.disconnect()
    assert.equal(nextTimerIn(), null)
  },

  connect_after_disconnect_opens_again() {
    store.connect()
    last().hello()
    store.disconnect()
    store.connect()
    assert.equal(sockets.length, 2)
    last().hello()
    assert.equal(store.connected, true)
  },
}

const name = process.argv[2]
if (name === '--list') {
  console.log(JSON.stringify(Object.keys(scenarios)))
} else {
  assert.ok(name in scenarios, `unknown scenario ${name}`)
  scenarios[name]()
  console.log('ok')
}
