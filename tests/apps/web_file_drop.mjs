// Scenarios for files dragged in from the computer, executed under Node against the real files —
// see `test_web_file_drop.py`. Run as `node … web_file_drop.mjs <scenario>`; a failed `assert`
// exits non-zero with the reason on stderr.
//
// Checked without a browser: which items of a drop are folders (by entry, and by reading a file the
// browser said nothing about), the size ceiling, the window's guard — the zone under the pointer,
// the drop effect it sets, when a drag counts as over (a drop, the pointer leaving the window,
// Escape, silence), a drag begun on the page left alone — and the slash menu's file command, which
// exists only where a file has somewhere to go.

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

const src = (path) => new URL(path, WEB_SRC).href

const { carriesFiles, droppedPaths, overLimit, settleDropped, sortDropped, sortFiles } = await import(src('shared/utils/fileDrop.ts'))
const { createFileDragTracker } = await import(src('shared/utils/fileDrag.ts'))

const shot = new File([new Uint8Array([1, 2, 3])], 'shot.png', { type: 'image/png' })
const makefile = new File(['all:\n'], 'Makefile')
const empty = new File([], '.gitkeep')
const folderAsFile = new File([], 'docs')

/** A drop item as the browser gives it: with an entry, or — `entry: null` — without one. */
function item(file, entry) {
  return {
    kind: 'file',
    getAsFile: () => file,
    ...(entry === undefined ? {} : { webkitGetAsEntry: () => entry }),
  }
}

const asFile = (file) => item(file, { isDirectory: false, name: file.name })
const asFolder = (file) => item(file, { isDirectory: true, name: file.name })

// ── The window's guard ────────────────────────────────────────────────────────

/** A fake element tree: a node knows its parent, nothing more is read. */
const page = { name: 'page', parent: null }
const sidebar = { name: 'sidebar', parent: page }
const card = { name: 'card', parent: page }
const cardRow = { name: 'row', parent: card }
const field = { name: 'field', parent: page }
const rules = { name: 'rules', parent: page }

function guard() {
  const zones = new Map([
    [card, { name: 'card', open: true, accepts() { return this.open } }],
    [field, { name: 'field', open: true, accepts() { return this.open } }],
    [rules, { name: 'rules', accepts: () => false }],
  ])
  const timers = []
  const states = []
  const tracker = createFileDragTracker({
    zoneOf: (target) => {
      for (let node = target; node; node = node.parent) if (zones.has(node)) return zones.get(node)
      return null
    },
    onState: (state) => states.push({ active: state.active, zone: state.zone?.name ?? null }),
    later: (run, ms) => {
      const timer = { run, ms, live: true }
      timers.push(timer)
      return () => { timer.live = false }
    },
  })
  const fire = (ms) => {
    for (const timer of timers.filter((one) => one.live && one.ms === ms)) {
      timer.live = false
      timer.run()
    }
  }
  return { tracker, zones, states, fire, timers }
}

function drag(type, target, { types = ['Files'], relatedTarget } = {}) {
  const event = {
    type,
    target,
    relatedTarget,
    dataTransfer: { types, dropEffect: 'unset' },
    prevented: false,
    preventDefault() { this.prevented = true },
  }
  return event
}

const last = (states) => states.at(-1)

const SCENARIOS = {
  'a-drop-of-only-file-addresses-names-the-files-and-nothing-else-does'() {
    const data = (types) => ({ getData: (format) => types[format] ?? '' })
    const path = 'file:///home/user/Downloads/Ilyahov_Pishi-sokrashchay_RuLit_Me.html'
    assert.deepEqual(droppedPaths(data({ 'text/uri-list': path })), ['Ilyahov_Pishi-sokrashchay_RuLit_Me.html'])
    // UTF-16 handed over as bytes: a zero after every character, read as `f i l e : / / /`.
    const wide = [...path].map((char) => `${char}\u0000`).join('')
    assert.deepEqual(droppedPaths(data({ 'text/plain': wide })), ['Ilyahov_Pishi-sokrashchay_RuLit_Me.html'])
    assert.deepEqual(
      droppedPaths(data({ 'text/uri-list': '# comment\r\nfile:///tmp/%D0%BE%D1%82%D1%87%D1%91%D1%82.pdf\r\nfile:///tmp/b.txt' })),
      ['отчёт.pdf', 'b.txt'],
    )
    // A link from a page, a mix, or plain text is not a file left behind: it stays what it is.
    assert.deepEqual(droppedPaths(data({ 'text/uri-list': 'https://example.com/a.pdf' })), [])
    assert.deepEqual(droppedPaths(data({ 'text/uri-list': `${path}\nhttps://example.com` })), [])
    assert.deepEqual(droppedPaths(data({ 'text/plain': 'просто текст' })), [])
    assert.deepEqual(droppedPaths(null), [])
  },

  'only-a-drag-with-files-carries-files'() {
    assert.equal(carriesFiles(['Files']), true)
    assert.equal(carriesFiles(['text/plain', 'Files']), true)
    assert.equal(carriesFiles(['text/plain', 'text/html']), false)
    assert.equal(carriesFiles([]), false)
    assert.equal(carriesFiles(null), false)
  },

  'over-the-ceiling-means-larger-as-the-server-counts'() {
    assert.equal(overLimit(10, 10), false)
    assert.equal(overLimit(11, 10), true)
    assert.equal(overLimit(0, 10), false)
    // The ceiling not known yet: nothing is refused on this side.
    assert.equal(overLimit(10 ** 12, null), false)
    assert.equal(overLimit(10 ** 12, undefined), false)
  },

  async 'a-folder-is-told-by-its-entry-and-the-files-beside-it-stay'() {
    const sorted = sortDropped({
      files: [shot, folderAsFile, makefile],
      items: [asFile(shot), asFolder(folderAsFile), asFile(makefile)],
    })
    assert.deepEqual(sorted.files, [shot, makefile])
    assert.deepEqual(sorted.folders, ['docs'])
    // An entry said "file": nothing is left to read.
    assert.deepEqual(sorted.unsure, [])
    assert.deepEqual(await settleDropped(sorted, () => { throw new Error('read nothing') }), {
      files: [shot, makefile],
      folders: ['docs'],
    })
  },

  async 'without-entries-a-typeless-file-is-read-and-a-folder-does-not-read'() {
    const readable = async (file) => file !== folderAsFile
    // No entry API at all.
    const bare = sortDropped({
      files: [shot, folderAsFile, makefile, empty],
      items: [item(shot), item(folderAsFile), item(makefile), item(empty)],
    })
    // A typed file is a file at once; the type-less ones wait for the reading.
    assert.deepEqual(bare.unsure, [folderAsFile, makefile, empty])
    assert.deepEqual(await settleDropped(bare, readable), {
      files: [shot, makefile, empty],
      folders: ['docs'],
    })

    // An entry API that answers nothing for an item, and a drop with no items list at all.
    const nulls = sortDropped({ files: [folderAsFile], items: [item(folderAsFile, null)] })
    assert.deepEqual((await settleDropped(nulls, readable)).folders, ['docs'])
    const noItems = sortDropped({ files: [shot, folderAsFile] })
    assert.deepEqual(await settleDropped(noItems, readable), { files: [shot], folders: ['docs'] })
  },

  async 'a-real-empty-file-reads-and-goes'() {
    // The default reading, on real Blobs: an empty file is a file, not a folder.
    assert.deepEqual(await settleDropped(sortFiles([empty, makefile])), { files: [empty, makefile], folders: [] })
  },

  'a-drop-of-text-or-nothing-brings-no-files'() {
    assert.deepEqual(sortDropped(null), { files: [], folders: [], unsure: [] })
    assert.deepEqual(sortDropped({ files: [], items: [{ kind: 'string', getAsFile: () => null }] }), {
      files: [],
      folders: [],
      unsure: [],
    })
  },

  'the-zone-under-the-pointer-says-copy-everything-else-says-no'() {
    const { tracker, states } = guard()

    const enter = drag('dragenter', cardRow)
    tracker.handle(enter)
    // The page decides, not the browser: every files drag over the window is taken.
    assert.equal(enter.prevented, true)
    assert.equal(enter.dataTransfer.dropEffect, 'copy')
    assert.deepEqual(last(states), { active: true, zone: 'card' })

    for (const [target, effect, zone] of [
      [field, 'copy', 'field'],
      [sidebar, 'none', null],
      [rules, 'none', 'rules'],
      [page, 'none', null],
    ]) {
      const over = drag('dragover', target)
      tracker.handle(over)
      assert.equal(over.prevented, true, target.name)
      assert.equal(over.dataTransfer.dropEffect, effect, target.name)
      assert.deepEqual(last(states), { active: true, zone }, target.name)
    }
  },

  'a-zone-that-stops-taking-files-says-no-at-the-next-dragover'() {
    const { tracker, zones } = guard()
    zones.get(card).open = false
    const over = drag('dragover', cardRow)
    tracker.handle(over)
    assert.equal(over.dataTransfer.dropEffect, 'none')
  },

  'a-drop-anywhere-is-taken-from-the-browser-and-ends-the-drag'() {
    const { tracker, states } = guard()
    tracker.handle(drag('dragover', sidebar))
    const drop = drag('drop', sidebar)
    tracker.handle(drop)
    assert.equal(drop.prevented, true)
    assert.deepEqual(last(states), { active: false, zone: null })
  },

  'leaving-the-window-or-escape-ends-the-drag-after-a-beat'() {
    const { tracker, states, fire } = guard()
    tracker.handle(drag('dragover', field))
    // Moving between elements names the element entered: nothing ends.
    tracker.handle(drag('dragleave', field, { relatedTarget: sidebar }))
    fire(50)
    assert.deepEqual(last(states), { active: true, zone: 'field' })

    // Out of the window, or Escape: a leave with no element entered.
    tracker.handle(drag('dragleave', field, { relatedTarget: null }))
    assert.deepEqual(last(states), { active: true, zone: 'field' })
    fire(50)
    assert.deepEqual(last(states), { active: false, zone: null })
  },

  'a-null-leave-followed-by-a-dragover-is-a-boundary-not-an-end'() {
    // Safari names no element on every boundary.
    const { tracker, states, fire } = guard()
    tracker.handle(drag('dragover', field))
    tracker.handle(drag('dragleave', field, { relatedTarget: null }))
    tracker.handle(drag('dragenter', cardRow))
    fire(50)
    assert.deepEqual(last(states), { active: true, zone: 'card' })
  },

  'silence-ends-a-drag-the-events-never-closed'() {
    const { tracker, states, fire } = guard()
    tracker.handle(drag('dragover', field))
    fire(1500)
    assert.deepEqual(last(states), { active: false, zone: null })
  },

  'a-pointer-moving-again-means-the-drag-is-over'() {
    const { tracker, states } = guard()
    tracker.handle(drag('dragover', field))
    tracker.handle({ type: 'pointermove', target: field, preventDefault() {} })
    assert.deepEqual(last(states), { active: false, zone: null })
  },

  'a-drag-begun-on-the-page-is-left-alone-even-with-files-among-its-types'() {
    const { tracker, states } = guard()
    tracker.handle(drag('dragstart', field, { types: [] }))
    const over = drag('dragover', sidebar, { types: ['text/uri-list', 'Files'] })
    tracker.handle(over)
    assert.equal(over.prevented, false)
    assert.equal(over.dataTransfer.dropEffect, 'unset')
    const drop = drag('drop', field, { types: ['text/uri-list', 'Files'] })
    tracker.handle(drop)
    assert.equal(drop.prevented, false)
    assert.deepEqual(states, [])

    // Its source was removed mid-drag and its `dragend` went nowhere: the drop closed it, and the
    // next drag from the computer is the guard's again.
    const next = drag('dragover', sidebar)
    tracker.handle(next)
    assert.equal(next.prevented, true)
    assert.equal(next.dataTransfer.dropEffect, 'none')
  },

  'text-dragged-from-outside-is-not-the-guards'() {
    const { tracker, states } = guard()
    const over = drag('dragover', field, { types: ['text/plain'] })
    tracker.handle(over)
    assert.equal(over.prevented, false)
    assert.deepEqual(states, [])
  },

  async 'the-file-command-is-in-the-menu-only-where-a-file-has-somewhere-to-go'() {
    const { createSlashItems } = await import(src('components/markdown/editor/controls/slashMenu.ts'))
    const t = (key) => key
    const ids = (items) => items.map((one) => one.id)
    const full = new Set(['heading', 'list', 'entityRef', 'slash'])
    const noRefs = new Set(['heading', 'list', 'slash'])
    let picked = 0
    const pickFile = () => { picked += 1 }

    // No holder: no command.
    assert.equal(ids(createSlashItems(t, full)).includes('file'), false)
    // A holder, but a field that cannot show a code: no command either.
    assert.equal(ids(createSlashItems(t, noRefs, { pickFile })).includes('file'), false)

    const items = createSlashItems(t, full, { pickFile })
    const file = items.find((one) => one.id === 'file')
    assert.ok(file)
    assert.equal(file.title, 'common.editor.slash.file')
    assert.ok(file.keywords.includes('файл') && file.keywords.includes('image'))

    // Picking it removes the typed `/query` and opens the dialog in the same gesture.
    const calls = []
    const chain = {
      focus() { calls.push('focus'); return chain },
      deleteRange(range) { calls.push(['deleteRange', range]); return chain },
      run() { calls.push('run'); return true },
    }
    file.run({ chain: () => chain }, { from: 3, to: 8 })
    assert.deepEqual(calls, ['focus', ['deleteRange', { from: 3, to: 8 }], 'run'])
    assert.equal(picked, 1)
  },
}

const [, , scenario] = process.argv
if (scenario === '--list') {
  console.log(JSON.stringify(Object.keys(SCENARIOS)))
} else {
  await SCENARIOS[scenario]()
  console.log('ok')
}
