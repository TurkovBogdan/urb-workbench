// Scenarios for files pasted or dropped into an editor field, executed under Node against the real
// files — see `test_web_file_attach.py`. Run as `node … web_file_attach.mjs <scenario>`; a failed
// `assert` exits non-zero with the reason on stderr.
//
// What is checked is the extension's logic without a browser: which files a paste or a drop
// brings, the `data:` pictures of a clipboard's markup, the text that goes in for one, two or many
// files, `IMAGE@` against `FILE@`, and the placeholder — mapped through edits around it, settled
// into the codes in one transaction, or taken away with nothing written. The schema is a small
// stand-in with the same shape as the editor's: paragraphs, a code block, an inline atom `entityRef`.

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

const {
  DOCUMENT_REPLACED, addPlaceholder, dataImageFiles, insertionText, pastedFiles,
  placeholderAtSelection, placeholderPlugin, placeholderPos, sendable, settlePlaceholder, textAround,
  timeNamed,
} = await import(src('components/markdown/editor/behavior/fileAttach.ts'))
const { fileQuote, REF_CODE } = await import(src('components/markdown/shared/contracts.ts'))
const { Schema, Fragment } = await import(new URL('../../web/node_modules/@tiptap/pm/dist/model/index.js', import.meta.url).href)
const { EditorState, TextSelection } = await import(new URL('../../web/node_modules/@tiptap/pm/dist/state/index.js', import.meta.url).href)

const schema = new Schema({
  nodes: {
    doc: { content: 'block+' },
    paragraph: { group: 'block', content: 'inline*' },
    codeBlock: { group: 'block', content: 'text*', code: true, marks: '' },
    text: { group: 'inline' },
    entityRef: { group: 'inline', inline: true, atom: true, attrs: { code: { default: '' } } },
  },
})

// The editor parses the codes through its bridge; the stand-in cuts them out of the text the same
// way, and drops the blanks at the edges as markdown drops them at a paragraph's.
function contentFor(raw) {
  const text = raw.trim()
  const nodes = []
  let at = 0
  for (const match of text.matchAll(new RegExp(REF_CODE.source, 'gi'))) {
    if (match.index > at) nodes.push(schema.text(text.slice(at, match.index)))
    nodes.push(schema.nodes.entityRef.create({ code: match[0].toUpperCase() }))
    at = match.index + match[0].length
  }
  if (at < text.length) nodes.push(schema.text(text.slice(at)))
  return Fragment.fromArray(nodes)
}

function paragraph(...parts) {
  return schema.node('paragraph', null, parts.map((part) =>
    typeof part === 'string' ? schema.text(part) : schema.nodes.entityRef.create({ code: part.code })))
}

function stateOf(...blocks) {
  return EditorState.create({ doc: schema.node('doc', null, blocks), plugins: [placeholderPlugin()] })
}

/** The document as text, an atom as `[CODE]`. */
function textOf(state) {
  const lines = []
  state.doc.forEach((block) => {
    let line = ''
    block.forEach((child) => { line += child.isText ? child.text : `[${child.attrs.code}]` })
    lines.push(line)
  })
  return lines.join('\n')
}

const render = () => { throw new Error('a placeholder is not drawn under Node') }

function withPlaceholder(state, id, pos, end = pos) {
  return state.apply(addPlaceholder(state.tr, id, pos, render, end))
}

/** The whole document replaced by another, as the editor loads a value from outside. */
function replaceWhole(state, ...blocks) {
  return state.tr.replaceWith(0, state.doc.content.size, blocks)
}

function clipboard({ plain = '', html = '', files = [] } = {}) {
  return { files, getData: (format) => (format === 'text/plain' ? plain : format === 'text/html' ? html : '') }
}

const PNG = Uint8Array.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a, 1, 2, 3])
const PNG_B64 = Buffer.from(PNG).toString('base64')
const shot = new File([PNG], 'image.png', { type: 'image/png' })
const log = new File(['line\n'], 'build.log', { type: 'text/plain' })
// Local time: the name carries the moment the person sees on their clock.
const NOW = new Date(2026, 9, 26, 14, 3, 7)
const STAMP = '2026-10-26-14-03-07'

const A = 'IMAGE@0123456789'
const B = 'IMAGE@ABCDEF0123'
const C = 'FILE@1111111111'

const SCENARIOS = {
  'insertion-text-for-one-two-and-many'() {
    assert.equal(insertionText([], '', ''), '')
    assert.equal(insertionText([A], '', ''), A)
    assert.equal(insertionText([A, B], '', ''), `${A} ${B}`)
    assert.equal(insertionText([A, B, C], '', ''), `${A} ${B} ${C}`)
    // A file that did not make it leaves no gap behind.
    assert.equal(insertionText([A, '', C], '', ''), `${A} ${C}`)
  },

  'insertion-text-keeps-a-blank-from-its-neighbours'() {
    assert.equal(insertionText([A], 'x', 'y'), ` ${A} `)
    assert.equal(insertionText([A], ' ', ' '), A)
    assert.equal(insertionText([A], '\n', ''), A)
    // A pill or a picture next to the spot counts as a word.
    assert.equal(insertionText([A], '￼', ''), ` ${A}`)
  },

  'a-picture-is-quoted-as-image-the-rest-as-file'() {
    assert.equal(fileQuote('FILE@0123456789', 'image'), 'IMAGE@0123456789')
    assert.equal(fileQuote('FILE@0123456789', 'document'), 'FILE@0123456789')
    assert.equal(fileQuote('IMAGE@0123456789', 'text'), 'FILE@0123456789')
    assert.equal(fileQuote('0123456789', 'image'), 'IMAGE@0123456789')
  },

  'a-paste-brings-files-unless-it-is-text-with-its-markup'() {
    const names = (files) => files.map((file) => file.name)
    // A screenshot; a picture copied in a browser; a file copied in a file manager.
    assert.deepEqual(names(pastedFiles(clipboard({ files: [shot] }), NOW)), [`screenshot-${STAMP}.png`])
    assert.deepEqual(
      names(pastedFiles(clipboard({ html: '<img src="https://x/y.png">', files: [shot] }), NOW)),
      [`screenshot-${STAMP}.png`],
    )
    assert.deepEqual(pastedFiles(clipboard({ plain: 'build.log', files: [log] })), [log])
    // Cells of a table put a picture of themselves beside the text: that is a paste of text.
    assert.deepEqual(pastedFiles(clipboard({ plain: 'a\tb', html: '<table></table>', files: [shot] })), [])
    assert.deepEqual(pastedFiles(clipboard({ plain: `see ${A}` })), [])
    assert.deepEqual(pastedFiles(clipboard()), [])
    assert.deepEqual(pastedFiles(null), [])
  },

  'a-data-picture-of-the-markup-is-a-file-when-nothing-else-came'() {
    const html = `<p><img alt="" src="data:image/png;base64,${PNG_B64}"><img src='data:image/jpeg;base64,${PNG_B64}'></p>`
    const files = pastedFiles(clipboard({ html }), NOW)
    assert.deepEqual(files.map((file) => [file.name, file.type, file.size]), [
      [`screenshot-${STAMP}-1.png`, 'image/png', PNG.length],
      [`screenshot-${STAMP}-2.jpg`, 'image/jpeg', PNG.length],
    ])
    // With text beside it the markup stays a paste of text; an address is not fetched.
    assert.deepEqual(pastedFiles(clipboard({ plain: 'caption', html })), [])
    assert.deepEqual(pastedFiles(clipboard({ html: '<img src="https://example.com/a.png">' })), [])
  },

  async 'only-an-unnamed-picture-is-named-by-the-time-of-the-paste'() {
    const pdf = new File(['%PDF'], 'image.pdf', { type: 'application/pdf' })
    const photo = new File([PNG], 'отпуск.png', { type: 'image/png' })
    const second = new File([PNG], 'image.jpeg', { type: 'image/jpeg' })
    const named = timeNamed([pdf, shot, photo, second], NOW)
    assert.deepEqual(named.map((file) => file.name), [
      'image.pdf', `screenshot-${STAMP}-1.png`, 'отпуск.png', `screenshot-${STAMP}-2.jpeg`,
    ])
    assert.equal(named[0], pdf)
    assert.equal(named[2], photo)
    // A numbered name is a file's own: only the browser's bare `image.<ext>` means none.
    const numbered = new File([PNG], 'image-3.png', { type: 'image/png' })
    assert.equal(timeNamed([numbered], NOW)[0], numbered)
    assert.equal(named[1].type, 'image/png')
    assert.deepEqual(new Uint8Array(await named[1].arrayBuffer()), PNG)
    // A paste of a PDF copied in a file manager keeps the file as it came.
    assert.deepEqual(pastedFiles(clipboard({ files: [pdf] }), NOW), [pdf])
    // Single digits of the clock are padded; nothing else is touched.
    assert.equal(timeNamed([shot], new Date(2026, 0, 2, 3, 4, 5))[0].name, 'screenshot-2026-01-02-03-04-05.png')
  },

  async 'a-data-picture-keeps-its-bytes-and-a-broken-one-is-skipped'() {
    const [file] = dataImageFiles(`<img src="data:image/svg+xml;base64,${PNG_B64}"><img src="data:image/png;base64,@@@">`)
    assert.equal(file.name, 'image-1.svg')
    assert.deepEqual(new Uint8Array(await file.arrayBuffer()), PNG)
    assert.equal(dataImageFiles('<img src="data:image/png;base64,@@@">').length, 0)
  },

  'folders-and-refusals-are-said-and-left-out-the-rest-goes-in-order'() {
    const said = { folders: [], refused: [] }
    const report = {
      onFolders: (names) => said.folders.push(...names),
      onRefused: (reason) => said.refused.push(reason),
    }
    const big = new File([new Uint8Array(32)], 'big.bin', { type: 'application/octet-stream' })
    const refuse = (file) => (file.size > 16 ? `${file.name} is over the ceiling` : null)

    assert.deepEqual(sendable([shot, big, log], ['docs'], refuse, report), [shot, log])
    assert.deepEqual(said, { folders: ['docs'], refused: ['big.bin is over the ceiling'] })

    // Without a refusal every file goes; with no folders nothing is said about them.
    said.folders.length = 0
    said.refused.length = 0
    assert.deepEqual(sendable([shot, big], [], undefined, report), [shot, big])
    assert.deepEqual(said, { folders: [], refused: [] })
  },

  'the-placeholder-follows-edits-before-it-and-ignores-those-after'() {
    // "hello world": the placeholder after "hello" — position 6 (1 opens the paragraph).
    let state = withPlaceholder(stateOf(paragraph('hello world')), 1, 6)
    assert.equal(placeholderPos(state, 1), 6)

    state = state.apply(state.tr.insertText('AB ', 1))
    assert.equal(placeholderPos(state, 1), 9)
    // " world" after the spot goes; the spot stays.
    state = state.apply(state.tr.delete(9, 15))
    assert.equal(placeholderPos(state, 1), 9)
    // Typing at the very spot goes after the placeholder.
    state = state.apply(state.tr.insertText('!', 9))
    assert.equal(placeholderPos(state, 1), 9)
    assert.equal(textOf(state), 'AB hello!')

    const settled = state.apply(settlePlaceholder(state, 1, [A, B], contentFor))
    assert.equal(textOf(settled), `AB hello [${A}] [${B}] !`)
    assert.equal(placeholderPos(settled, 1), null)
  },

  'a-placeholder-whose-text-was-deleted-still-lands-whole'() {
    let state = withPlaceholder(stateOf(paragraph('one two three')), 7, 5)
    state = state.apply(state.tr.delete(2, 10))
    const pos = placeholderPos(state, 7)
    assert.equal(pos, 2)
    const settled = state.apply(settlePlaceholder(state, 7, [C], contentFor))
    assert.equal(textOf(settled), `o [${C}] hree`)
  },

  'two-placeholders-settle-each-in-its-place'() {
    let state = withPlaceholder(stateOf(paragraph('ab'), paragraph('cd')), 1, 2)
    state = withPlaceholder(state, 2, 6)
    state = state.apply(settlePlaceholder(state, 2, [B], contentFor))
    state = state.apply(settlePlaceholder(state, 1, [A], contentFor))
    assert.equal(textOf(state), `a [${A}] b\nc [${B}] d`)
  },

  'nothing-made-it-and-nothing-is-written'() {
    const state = withPlaceholder(stateOf(paragraph('hello')), 3, 6)
    const tr = settlePlaceholder(state, 3, [], contentFor)
    assert.equal(tr.docChanged, false)
    const after = state.apply(tr)
    assert.equal(textOf(after), 'hello')
    assert.equal(placeholderPos(after, 3), null)
    // A placeholder already gone answers with no transaction at all.
    assert.equal(settlePlaceholder(after, 3, [A], contentFor), null)
  },

  'codes-next-to-a-picture-are-a-blank-apart'() {
    let state = withPlaceholder(stateOf(paragraph({ code: A })), 4, 2)
    assert.deepEqual(textAround(state.doc, 2), { before: '￼', after: '' })
    state = state.apply(settlePlaceholder(state, 4, [B], contentFor))
    assert.equal(textOf(state), `[${A}] [${B}]`)
  },

  'in-a-code-block-the-codes-are-plain-text'() {
    let state = withPlaceholder(stateOf(schema.node('codeBlock', null, [schema.text('x = 1')])), 5, 6)
    state = state.apply(settlePlaceholder(state, 5, [A], contentFor))
    assert.equal(textOf(state), `x = 1 ${A}`)
  },

  'the-caret-left-at-the-spot-moves-past-the-codes'() {
    let state = withPlaceholder(stateOf(paragraph('ab')), 6, 2)
    state = state.apply(state.tr.setSelection(TextSelection.create(state.doc, 2)))
    state = state.apply(settlePlaceholder(state, 6, [A, B], contentFor))
    // a, then blank, A, blank, B, blank (an atom is one position) → the caret before "b".
    assert.equal(state.selection.from, 2 + 5)
    assert.equal(state.doc.textBetween(state.selection.from, state.selection.from + 1), 'b')
  },

  'a-document-replaced-whole-cancels-the-pending-insertion'() {
    // The reviewer's case: the field loads another task's value while the upload is in flight.
    let state = withPlaceholder(stateOf(paragraph('alpha beta')), 8, 6)
    state = state.apply(replaceWhole(state, paragraph('task Y context'), paragraph('second')))

    assert.equal(placeholderPos(state, 8), null)
    assert.equal(settlePlaceholder(state, 8, [A], contentFor), null)
    assert.equal(textOf(state), 'task Y context\nsecond')
  },

  'a-value-loaded-from-outside-cancels-even-a-small-change'() {
    let state = withPlaceholder(stateOf(paragraph('alpha beta')), 9, 6)
    state = state.apply(state.tr.insertText('!', 11).setMeta(DOCUMENT_REPLACED, true))

    assert.equal(placeholderPos(state, 9), null)
    assert.equal(settlePlaceholder(state, 9, [A], contentFor), null)
  },

  'typing-around-a-placeholder-does-not-cancel-it'() {
    let state = withPlaceholder(stateOf(paragraph('alpha beta')), 10, 6)
    state = state.apply(state.tr.insertText('X', 1))
    state = state.apply(state.tr.delete(9, 13))

    assert.equal(placeholderPos(state, 10), 7)
  },

  'a-paste-over-a-selection-that-all-failed-keeps-the-text'() {
    // "alpha beta gamma": "beta" (7–11) is selected when the files are pasted.
    let state = stateOf(paragraph('alpha beta gamma'))
    state = state.apply(state.tr.setSelection(TextSelection.create(state.doc, 7, 11)))
    const begun = placeholderAtSelection(state, 11, render)
    assert.equal(begun.docChanged, false)
    state = state.apply(begun)
    assert.equal(textOf(state), 'alpha beta gamma')

    const tr = settlePlaceholder(state, 11, [], contentFor)
    state = state.apply(tr)

    assert.equal(tr.docChanged, false)
    assert.equal(textOf(state), 'alpha beta gamma')
    assert.equal(placeholderPos(state, 11), null)
  },

  'a-paste-over-a-selection-replaces-it-with-the-codes'() {
    let state = stateOf(paragraph('alpha beta gamma'))
    state = state.apply(state.tr.setSelection(TextSelection.create(state.doc, 7, 11)))
    state = state.apply(placeholderAtSelection(state, 12, render))
    state = state.apply(state.tr.insertText('>', 1))
    state = state.apply(settlePlaceholder(state, 12, [A, C], contentFor))

    assert.equal(textOf(state), `>alpha [${A}] [${C}] gamma`)
  },
}

const [, , scenario] = process.argv
if (scenario === '--list') {
  console.log(JSON.stringify(Object.keys(SCENARIOS)))
} else {
  await SCENARIOS[scenario]()
  console.log('ok')
}
