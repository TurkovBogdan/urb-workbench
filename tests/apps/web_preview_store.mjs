// Scenarios for the preview store (`web/src/stores/preview.ts`), executed under Node against the
// real file — see `test_web_preview_store.py`. Run as `node … web_preview_store.mjs <scenario>`;
// a failed `assert` exits non-zero with the reason on stderr.
//
// Two neighbours are replaced: the lookup client (`@/api/lookup`) answers from a table the
// scenario controls and records every request, and the change feed (`@/stores/changes`) hands the
// scenario the subscribed handlers so it can play events into them. Vue, Pinia and the store are
// the real code.

import assert from 'node:assert/strict'
import { register } from 'node:module'

const WEB_SRC = new URL('../../web/src/', import.meta.url)

const FAKES = {
  '@/api/lookup': `
    export const PREVIEW_BATCH_MAX = 200
    export function fetchPreviews(codes, workspace, holder = null) { return globalThis.lookupFake(codes, workspace, holder) }
  `,
  '@/stores/changes': `
    export const ANY_ENTITY = '*'
    export function useChangesStore() { return globalThis.feedFake }
  `,
}

register(
  'data:text/javascript,' +
    encodeURIComponent(`
      const WEB_SRC = ${JSON.stringify(WEB_SRC.href)}
      const HARNESS = ${JSON.stringify(import.meta.url)}
      const FAKES = ${JSON.stringify(FAKES)}
      export async function resolve(specifier, context, next) {
        if (specifier in FAKES) {
          return { url: 'data:text/javascript,' + encodeURIComponent(FAKES[specifier]), shortCircuit: true }
        }
        if (specifier.startsWith('@/')) return next(WEB_SRC + specifier.slice(2) + '.ts', context)
        if (context.parentURL === HARNESS && /^[a-z]/.test(specifier) && !specifier.startsWith('node:')) {
          return next(specifier, { ...context, parentURL: WEB_SRC + 'main.ts' })
        }
        return next(specifier, context)
      }
    `),
)

// ── the backend ──────────────────────────────────────────────────────────────
/** Every request: the codes and the workspace, plus a way to answer it later. */
const requests = []
/** What the backend says per code; a code missing here is answered `not_found`. */
const titles = new Map()

function record(code, workspace) {
  const title = titles.get(code)
  return title === undefined
    ? { code, title: '', description: '', link: '', error: { code: 'not_found', message: 'No such entity.' } }
    : { code, title: `${title}${workspace ? ` in ${workspace}` : ''}`, description: '', link: `/x/${code}`, error: null }
}

globalThis.lookupFake = (codes, workspace, holder) =>
  new Promise((resolve, reject) => {
    const place = holder ? `${workspace} for ${holder}` : workspace
    requests.push({ codes, workspace, holder, answer: () => resolve(codes.map((code) => record(code, place))), fail: reject })
  })

/** Answer every pending request, in order, and let the store take the answers in. */
async function answerAll() {
  for (const request of requests.splice(0)) request.answer()
  await tick()
}

const tick = () => new Promise((resolve) => setTimeout(resolve, 0))

// ── the feed ─────────────────────────────────────────────────────────────────
const subscriptions = []
const resyncHandlers = []
globalThis.feedFake = {
  on(entity, handler, options = {}) {
    subscriptions.push({ entity, handler, options })
    return () => {}
  },
  onResync(handler) {
    resyncHandlers.push(handler)
    return () => {}
  },
}

function feed(entity, event, ...ids) {
  for (const { handler } of subscriptions) handler({ entity, event, ids, refs: [], own: true })
}

const { createPinia, setActivePinia } = await import('pinia')
setActivePinia(createPinia())
const { usePreviewStore } = await import('@/stores/preview')

const store = usePreviewStore()

/** Load codes and settle: the state every scenario after the first starts from. */
async function loaded(...codes) {
  store.ensure(codes)
  await tick()
  await answerAll()
}

const asked = () => requests.map((request) => request.codes)

// ── scenarios ────────────────────────────────────────────────────────────────
const scenarios = {
  codes_of_one_tick_go_out_in_one_request() {
    store.ensure(['TASK@1', 'TASK@2'])
    store.ensure(['TASK@2', 'NOTE@3'])
    assert.equal(requests.length, 0, 'nothing leaves before the tick ends')
    return tick().then(() => {
      assert.deepEqual(asked(), [['TASK@1', 'TASK@2', 'NOTE@3']])
    })
  },

  only_missing_codes_are_asked_and_misses_are_kept() {
    titles.set('TASK@1', 'One')
    return loaded('TASK@1', 'TASK@404').then(async () => {
      assert.equal(store.get('TASK@1').title, 'One')
      assert.equal(store.get('TASK@404').error.code, 'not_found')
      store.ensure(['TASK@1', 'TASK@404', 'TASK@2'])
      await tick()
      assert.deepEqual(asked(), [['TASK@2']], 'a known code and a known miss stay home')
    })
  },

  the_store_listens_to_every_entity_including_its_own_tab() {
    assert.deepEqual(
      subscriptions.map(({ entity, options }) => [entity, options.own]),
      [['*', true]],
    )
    assert.equal(resyncHandlers.length, 1)
  },

  a_change_re_asks_only_the_held_codes_it_names() {
    titles.set('TASK@1', 'One')
    return loaded('TASK@1', 'TASK@2').then(async () => {
      titles.set('TASK@1', 'Renamed')
      feed('tasks.task', 'updated', 'TASK@1', 'TASK@99')
      await tick()
      assert.deepEqual(asked(), [['TASK@1']])
      assert.equal(store.get('TASK@1').title, 'One', 'the old record stays on screen meanwhile')
      await answerAll()
      assert.equal(store.get('TASK@1').title, 'Renamed')
    })
  },

  a_file_change_re_asks_the_file_under_either_word() {
    titles.set('IMAGE@AB12', 'Shot')
    return loaded('IMAGE@AB12', 'TASK@1').then(async () => {
      titles.set('IMAGE@AB12', 'Renamed shot')
      // The feed names a file by `FILE@`; the body quotes it as a picture.
      feed('tasks.file', 'updated', 'FILE@AB12')
      await tick()
      assert.deepEqual(asked(), [['IMAGE@AB12']])
      await answerAll()
      assert.equal(store.get('IMAGE@AB12').title, 'Renamed shot')
    })
  },

  wide_events_re_ask_the_whole_map() {
    return loaded('TASK@1', 'STAGE@2').then(async () => {
      for (const [entity, event, ids] of [
        ['tasks.task', 'deleted', ['TASK@7']],
        ['codex.mount', 'updated', ['CODEX@8']],
        ['tasks.task', 'updated', []],
      ]) {
        feed(entity, event, ...ids)
        await tick()
        assert.deepEqual(asked(), [['TASK@1', 'STAGE@2']], `${entity} ${event}`)
        await answerAll()
      }
      resyncHandlers[0]()
      await tick()
      assert.deepEqual(asked(), [['TASK@1', 'STAGE@2']], 'resync')
    })
  },

  refresh_all_re_asks_every_held_code() {
    return loaded('TASK@1', 'NOTE@2').then(async () => {
      store.refreshAll()
      await tick()
      assert.deepEqual(asked(), [['TASK@1', 'NOTE@2']])
    })
  },

  a_code_changed_while_in_flight_is_asked_again_after_the_answer() {
    titles.set('TASK@1', 'Before')
    store.ensure(['TASK@1'])
    return tick().then(async () => {
      feed('tasks.task', 'updated', 'TASK@1')
      await tick()
      assert.equal(requests.length, 1, 'no second request while the first is out')
      titles.set('TASK@1', 'After')
      requests.shift().answer()
      await tick()
      assert.deepEqual(asked(), [['TASK@1']], 'asked again once the answer landed')
      await answerAll()
      assert.equal(store.get('TASK@1').title, 'After')
    })
  },

  a_workspace_switch_drops_the_map_and_answers_of_the_old_one() {
    titles.set('TASK@1', 'One')
    store.setWorkspace('WORKSPACE@A')
    return loaded('TASK@1').then(async () => {
      assert.equal(store.get('TASK@1').title, 'One in WORKSPACE@A')
      store.ensure(['TASK@2'])
      await tick()
      store.setWorkspace('WORKSPACE@B')
      assert.equal(store.get('TASK@1'), undefined, 'dropped at once')
      await tick()
      assert.deepEqual(
        requests.map((request) => [request.codes, request.workspace]),
        [
          [['TASK@2'], 'WORKSPACE@A'],
          [['TASK@1', 'TASK@2'], 'WORKSPACE@B'],
        ],
      )
      requests.shift().answer()
      await tick()
      assert.equal(store.get('TASK@2'), undefined, 'the old workspace answer is not taken')
      await answerAll()
      assert.equal(store.get('TASK@1').title, 'One in WORKSPACE@B')
    })
  },

  a_code_under_two_workspaces_has_a_record_in_each() {
    titles.set('TASK@1', 'One')
    store.setWorkspace('WORKSPACE@A')
    store.ensure(['TASK@1'])
    store.ensure(['TASK@1'], 'WORKSPACE@B')
    return tick().then(async () => {
      assert.deepEqual(
        requests.map((request) => [request.codes, request.workspace]),
        [
          [['TASK@1'], 'WORKSPACE@A'],
          [['TASK@1'], 'WORKSPACE@B'],
        ],
      )
      await answerAll()
      assert.equal(store.get('TASK@1').title, 'One in WORKSPACE@A', 'unnamed — the selected one')
      assert.equal(store.get('TASK@1', 'WORKSPACE@A').title, 'One in WORKSPACE@A')
      assert.equal(store.get('TASK@1', 'WORKSPACE@B').title, 'One in WORKSPACE@B')
    })
  },

  an_answer_lands_only_in_the_workspace_it_was_asked_under() {
    titles.set('TASK@1', 'One')
    store.setWorkspace('WORKSPACE@A')
    store.ensure(['TASK@1'], 'WORKSPACE@B')
    return tick().then(async () => {
      await answerAll()
      assert.equal(store.get('TASK@1', 'WORKSPACE@B').title, 'One in WORKSPACE@B')
      assert.equal(store.get('TASK@1'), undefined, 'the selected workspace never asked it')
      store.ensure(['TASK@1'])
      await tick()
      assert.deepEqual(asked(), [['TASK@1']], 'asked under the selected one on its own')
      assert.equal(requests[0].workspace, 'WORKSPACE@A')
    })
  },

  a_page_s_workspace_outlives_a_sidebar_switch_and_goes_with_the_page() {
    titles.set('TASK@1', 'One')
    store.setWorkspace('WORKSPACE@B')
    store.retain('WORKSPACE@B')
    store.ensure(['TASK@1'], 'WORKSPACE@B')
    return tick().then(async () => {
      await answerAll()
      store.setWorkspace('WORKSPACE@A')
      assert.equal(store.get('TASK@1', 'WORKSPACE@B').title, 'One in WORKSPACE@B', 'the page keeps it')
      await tick()
      assert.deepEqual(
        requests.map((request) => [request.codes, request.workspace]),
        [[['TASK@1'], 'WORKSPACE@A']],
        'the sidebar asks its codes under the new workspace, the page asks nothing again',
      )
      await answerAll()
      store.release('WORKSPACE@B')
      assert.equal(store.get('TASK@1', 'WORKSPACE@B'), undefined, 'dropped with its last page')
      assert.equal(store.get('TASK@1').title, 'One in WORKSPACE@A')
    })
  },

  a_change_re_asks_a_code_in_every_workspace_holding_it() {
    titles.set('TASK@1', 'One')
    store.setWorkspace('WORKSPACE@A')
    store.retain('WORKSPACE@B')
    store.ensure(['TASK@1', 'TASK@2'])
    store.ensure(['TASK@1'], 'WORKSPACE@B')
    return tick().then(async () => {
      await answerAll()
      feed('tasks.task', 'updated', 'TASK@1')
      await tick()
      assert.deepEqual(
        requests.map((request) => [request.codes, request.workspace]).sort((a, b) => a[1].localeCompare(b[1])),
        [
          [['TASK@1'], 'WORKSPACE@A'],
          [['TASK@1'], 'WORKSPACE@B'],
        ],
      )
    })
  },

  a_page_s_entity_keeps_its_own_records_and_is_sent_along() {
    titles.set('FILE@1', 'Shot')
    store.setWorkspace('WORKSPACE@A')
    store.retain('WORKSPACE@A', 'TASK@T')
    store.ensure(['FILE@1'])
    store.ensure(['FILE@1'], 'WORKSPACE@A', 'TASK@T')
    return tick().then(async () => {
      assert.deepEqual(
        requests.map((request) => [request.codes, request.workspace, request.holder])
          .sort((a, b) => (a[2] === null ? -1 : 1) - (b[2] === null ? -1 : 1)),
        [
          [['FILE@1'], 'WORKSPACE@A', null],
          [['FILE@1'], 'WORKSPACE@A', 'TASK@T'],
        ],
      )
      await answerAll()
      assert.equal(store.get('FILE@1').title, 'Shot in WORKSPACE@A')
      assert.equal(store.get('FILE@1', 'WORKSPACE@A', 'TASK@T').title, 'Shot in WORKSPACE@A for TASK@T')
      store.release('WORKSPACE@A', 'TASK@T')
      assert.equal(store.get('FILE@1', 'WORKSPACE@A', 'TASK@T'), undefined, 'dropped with its page')
      assert.equal(store.get('FILE@1').title, 'Shot in WORKSPACE@A', 'the sidebar map stays')
    })
  },

  a_long_batch_is_split_at_the_backend_limit() {
    store.ensure(Array.from({ length: 450 }, (_, n) => `TASK@${n}`))
    return tick().then(() => {
      assert.deepEqual(asked().map((codes) => codes.length), [200, 200, 50])
    })
  },

  the_same_workspace_again_keeps_the_map() {
    store.setWorkspace('WORKSPACE@A')
    return loaded('TASK@1').then(async () => {
      store.setWorkspace('WORKSPACE@A')
      await tick()
      assert.ok(store.get('TASK@1'), 'still there')
      assert.equal(requests.length, 0, 'nothing re-asked')
    })
  },

  a_code_the_answer_lacks_is_failed_not_missing() {
    globalThis.lookupFake = (codes) => Promise.resolve(codes.slice(1).map((code) => record(code, null)))
    store.ensure(['TASK@1', 'TASK@2'])
    return tick().then(async () => {
      await tick()
      assert.equal(store.get('TASK@1').error.code, 'failed')
      assert.equal(store.get('TASK@2').error.code, 'not_found', 'its neighbour got its own answer')
    })
  },

  a_held_miss_is_re_asked_when_its_entity_appears() {
    return loaded('TASK@9').then(async () => {
      assert.equal(store.get('TASK@9').error.code, 'not_found')
      titles.set('TASK@9', 'Born')
      feed('tasks.task', 'created', 'TASK@9')
      await tick()
      await answerAll()
      assert.equal(store.get('TASK@9').title, 'Born')
    })
  },

  a_failed_request_leaves_failed_records() {
    store.ensure(['TASK@1'])
    return tick().then(async () => {
      requests.shift().fail(new Error('offline'))
      await tick()
      assert.equal(store.get('TASK@1').error.code, 'failed')
    })
  },
}

const name = process.argv[2]
if (name === '--list') {
  console.log(JSON.stringify(Object.keys(scenarios)))
} else {
  assert.ok(name in scenarios, `unknown scenario ${name}`)
  await scenarios[name]()
  console.log('ok')
}
