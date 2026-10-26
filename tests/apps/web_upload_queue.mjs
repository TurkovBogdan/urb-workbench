// Scenarios for the files card's upload queue, executed under Node against the real file — see
// `test_web_upload_queue.py`. Run as `node … web_upload_queue.mjs <scenario>`; a failed `assert`
// exits non-zero with the reason on stderr.
//
// The card outlives its holder: the task page keeps its components when the person follows a link
// to another task. What is checked is that a file goes to the holder it was dropped on, whatever
// the card shows by the time its turn comes, and that a row is shown on its own holder only.

import assert from 'node:assert/strict'
import { register } from 'node:module'

const WEB_SRC = new URL('../../web/src/', import.meta.url)

register(
  'data:text/javascript,' +
    encodeURIComponent(`
      const WEB_SRC = ${JSON.stringify(WEB_SRC.href)}
      export async function resolve(specifier, context, next) {
        if (specifier.startsWith('@/')) return next(WEB_SRC + specifier.slice(2) + '.ts', context)
        if (specifier.startsWith('.') && !/\\.[a-z]+$/.test(specifier) && context.parentURL?.startsWith(WEB_SRC)) {
          return next(specifier + '.ts', context)
        }
        return next(specifier, context)
      }
    `),
)

const { createUploadQueue } = await import(new URL('components/files/uploadQueue.ts', WEB_SRC).href)

const file = (name) => new File([name], name, { type: 'text/plain' })

/** A holder's upload whose answers the scenario releases one by one. */
function holder(name) {
  const calls = []
  const send = (sent, progress) => new Promise((resolve) => {
    calls.push({ holder: name, file: sent.name, progress, resolve })
  })
  return { send, calls }
}

const settle = () => new Promise((resolve) => setTimeout(resolve, 0))

function queue() {
  const state = { rows: [] }
  const timers = []
  const q = createUploadQueue(state, { noticeMs: 10, later: (run) => timers.push(run) })
  return { q, state, timers }
}

const SCENARIOS = {
  async 'files-go-to-the-holder-they-were-dropped-on'() {
    const { q } = queue()
    const x = holder('X')
    const y = holder('Y')

    q.enqueue('TASK@X', x.send, [file('a'), file('b'), file('c')])
    await settle()
    // The person follows a link to Y while "a" is sending; the card now shows Y.
    q.enqueue('TASK@Y', y.send, [file('d')])
    for (let i = 0; i < 4; i += 1) {
      const pending = [...x.calls, ...y.calls].find((call) => !call.done)
      pending.done = true
      pending.resolve({ ok: true })
      await settle()
    }

    assert.deepEqual(x.calls.map((call) => call.file), ['a', 'b', 'c'])
    assert.deepEqual(y.calls.map((call) => call.file), ['d'])
  },

  async 'one-file-at-a-time-in-the-order-given'() {
    const { q } = queue()
    const x = holder('X')

    q.enqueue('TASK@X', x.send, [file('a'), file('b')])
    await settle()
    assert.deepEqual(x.calls.map((call) => call.file), ['a'])
    x.calls[0].resolve({ ok: true })
    await settle()
    assert.deepEqual(x.calls.map((call) => call.file), ['a', 'b'])
  },

  async 'a-row-shows-on-its-own-holder-only'() {
    const { q } = queue()
    const x = holder('X')

    q.enqueue('TASK@X', x.send, [file('a'), file('b')])
    await settle()
    x.calls[0].resolve({ ok: false, text: 'refused' })
    await settle()

    assert.deepEqual(q.rowsOf('TASK@Y'), [])
    assert.deepEqual(q.rowsOf('TASK@X').map((row) => [row.name, row.state]), [['a', 'failed'], ['b', 'sending']])
  },

  async 'progress-sent-and-dismissed'() {
    const { q } = queue()
    const x = holder('X')

    q.enqueue('TASK@X', x.send, [file('a')])
    await settle()
    x.calls[0].progress(0.5)
    assert.equal(q.rowsOf('TASK@X')[0].share, 0.5)
    x.calls[0].resolve({ ok: true })
    await settle()
    assert.deepEqual(q.rowsOf('TASK@X'), [])
  },

  async 'a-calm-outcome-fades-a-failure-waits'() {
    const { q, timers } = queue()
    const x = holder('X')

    q.enqueue('TASK@X', x.send, [file('a'), file('b')])
    await settle()
    x.calls[0].resolve({ ok: false, calm: true, text: 'is there already' })
    await settle()
    x.calls[1].resolve({ ok: false, text: 'too large' })
    await settle()
    assert.deepEqual(q.rowsOf('TASK@X').map((row) => row.state), ['notice', 'failed'])

    for (const run of timers) run()
    assert.deepEqual(q.rowsOf('TASK@X').map((row) => row.state), ['failed'])
    q.dismiss(q.rowsOf('TASK@X')[0].id)
    assert.deepEqual(q.rowsOf('TASK@X'), [])
  },

  async 'a-refusal-before-sending-is-a-failed-row-at-once-and-no-request'() {
    const { q } = queue()
    const x = holder('X')

    q.enqueue('TASK@X', x.send, [file('a')])
    await settle()
    // "a" is still sending: the folder dropped after it does not wait its turn.
    q.refuse('TASK@X', 'docs', '', 'folders are not uploaded')
    assert.deepEqual(
      q.rowsOf('TASK@X').map((row) => [row.name, row.state, row.text]),
      [['a', 'sending', ''], ['docs', 'failed', 'folders are not uploaded']],
    )
    assert.equal(x.calls.length, 1)
    assert.deepEqual(q.rowsOf('TASK@Y'), [])
  },

  async 'the-outcome-goes-out-with-its-holder-and-file'() {
    const state = { rows: [] }
    const outcomes = []
    const q = createUploadQueue(state, {
      noticeMs: 10,
      later: () => {},
      onOutcome: (holderCode, outcome) => outcomes.push([holderCode, outcome]),
    })
    const x = holder('X')

    q.enqueue('TASK@X', x.send, [file('a'), file('b')])
    await settle()
    x.calls[0].resolve({ ok: true, code: 'FILE@AAAAAAAAAA' })
    await settle()
    x.calls[1].resolve({ ok: false, calm: true, text: 'is there already', code: 'FILE@BBBBBBBBBB' })
    await settle()
    assert.deepEqual(outcomes, [
      ['TASK@X', { ok: true, code: 'FILE@AAAAAAAAAA' }],
      ['TASK@X', { ok: false, calm: true, text: 'is there already', code: 'FILE@BBBBBBBBBB' }],
    ])
  },
}

const [, , scenario] = process.argv
if (scenario === '--list') {
  console.log(JSON.stringify(Object.keys(SCENARIOS)))
} else {
  await SCENARIOS[scenario]()
  console.log('ok')
}
