// Scenarios for entity codes in an editor field, executed under Node against the real files — see
// `test_web_editor_pills.py`. Run as `node … web_editor_pills.mjs <scenario>`; a failed `assert`
// exits non-zero with the reason on stderr.
//
// What is checked is the bridge around a pill (`entityRef`): a code next to a word is printed as a
// word of its own and reads back as the same pill; a mark around a pill is one run in the text and
// in the document; a body loaded and saved unedited keeps its bytes, and an edit elsewhere keeps
// the codes and the marks. Edits and pastes are applied to a document of a small stand-in schema
// with the editor's node and mark names — the real one is assembled from Vue node views.

import assert from 'node:assert/strict'
import { register } from 'node:module'

const WEB_SRC = new URL('../../web/src/', import.meta.url)

register(
  'data:text/javascript,' +
    encodeURIComponent(`
      const WEB_SRC = ${JSON.stringify(WEB_SRC.href)}
      export async function resolve(specifier, context, next) {
        if (specifier.startsWith('@/')) return next(WEB_SRC + specifier.slice(2) + '.ts', context)
        // The sources import their neighbours without the extension, and a folder by its index,
        // as Vite allows.
        if (specifier.startsWith('.') && !/\\.[a-z]+$/.test(specifier) && context.parentURL?.startsWith(WEB_SRC)) {
          try {
            return await next(specifier + '.ts', context)
          } catch {
            return next(specifier + '/index.ts', context)
          }
        }
        return next(specifier, context)
      }
    `),
)

const src = (path) => new URL(path, WEB_SRC).href
const pm = (path) => new URL(`../../web/node_modules/@tiptap/pm/dist/${path}/index.js`, import.meta.url).href

const { markdownToDoc, docToMarkdown } = await import(src('components/markdown/editor/bridge/index.ts'))
const { pastedSlice } = await import(src('components/markdown/editor/behavior/markdownPaste.ts'))
const { resolveFeatures } = await import(src('components/markdown/editor/modes.ts'))
const { REF_CODE } = await import(src('components/markdown/shared/contracts.ts'))
const { TASK_BRIEF_FEATURES, TASK_DOCUMENT_FEATURES } = await import(src('features/tasks/editor.ts'))
const { CODEX_DOCUMENT_FEATURES } = await import(src('features/codex/editor.ts'))
const { Schema } = await import(pm('model'))
const { EditorState, TextSelection } = await import(pm('state'))

const FIELDS = {
  TASK_DOCUMENT_FEATURES: resolveFeatures('full', TASK_DOCUMENT_FEATURES),
  TASK_BRIEF_FEATURES: resolveFeatures('full', TASK_BRIEF_FEATURES),
  CODEX_DOCUMENT_FEATURES: resolveFeatures('full', CODEX_DOCUMENT_FEATURES),
}
const DOCUMENT = FIELDS.TASK_DOCUMENT_FEATURES

const schema = new Schema({
  nodes: {
    doc: { content: 'block+' },
    paragraph: { group: 'block', content: 'inline*' },
    heading: { group: 'block', content: 'inline*', attrs: { level: { default: 1 } } },
    quote: { group: 'block', content: 'inline*' },
    list: { group: 'block', content: 'listItem+' },
    listItem: {
      content: 'inline*',
      defining: true,
      attrs: { depth: { default: 0 }, ordered: { default: false }, checked: { default: null } },
    },
    table: { group: 'block', content: 'tableHead tableBody', isolating: true, attrs: { align: { default: [] } } },
    tableHead: { content: 'tableRow' },
    tableBody: { content: 'tableRow*' },
    tableRow: { content: 'tableCell+' },
    tableCell: { content: 'inline*', isolating: true, attrs: { header: { default: false } } },
    text: { group: 'inline' },
    hardBreak: { group: 'inline', inline: true },
    entityRef: { group: 'inline', inline: true, atom: true, attrs: { code: { default: '' } } },
  },
  marks: {
    bold: {},
    italic: {},
    strike: {},
    link: { attrs: { href: { default: '' } }, inclusive: false },
    code: { excludes: '_' },
  },
})

// Hex letters first: right after a code they extended it, and the code stopped being one.
const A = 'IMAGE@0123456789'
const B = 'IMAGE@ABCDEF0123'
const T = 'TASK@1A2B3C4D5E'
const F = 'FILE@FEEDFACE00'
const C = 'CODEX@C0DEC0DE00'

const pill = (code, marks = []) => ({ type: 'entityRef', attrs: { code }, ...(marks.length ? { marks } : {}) })
const text = (value, marks = []) => ({ type: 'text', text: value, ...(marks.length ? { marks } : {}) })
const paragraphOf = (...content) => ({ type: 'doc', content: [{ type: 'paragraph', content }] })
const bold = { type: 'bold' }

/** The text after a load and a save with nothing edited. */
const throughTheEditor = (value, features = DOCUMENT) => docToMarkdown(markdownToDoc(value, features))

/** The codes a text holds, in order, as the renderer and the parser find them. */
const codesIn = (value) => [...value.matchAll(REF_CODE)].map((match) => match[0].toUpperCase())

/** Every inline node of the document, flattened. */
function inlines(doc) {
  return (doc.content ?? []).flatMap((block) => block.content ?? [])
}

function loaded(value, features = DOCUMENT) {
  return EditorState.create({ doc: schema.nodeFromJSON(markdownToDoc(value, features)) })
}

const saved = (state) => docToMarkdown(state.doc.toJSON())

/** The position right after the text `needle` in the document. */
function after(state, needle) {
  let found = null
  state.doc.descendants((node, pos) => {
    if (found !== null || !node.isText) return
    const at = node.text.indexOf(needle)
    if (at >= 0) found = pos + at + needle.length
  })
  assert.notEqual(found, null, `no ${JSON.stringify(needle)} in the document`)
  return found
}

/** End of the `index`-th block's content. */
function endOfBlock(state, index) {
  let pos = 0
  for (let i = 0; i < index; i += 1) pos += state.doc.child(i).nodeSize
  return pos + state.doc.child(index).nodeSize - 1
}

function paste(state, value, from, to = from) {
  const at = state.apply(state.tr.setSelection(TextSelection.create(state.doc, from, to)))
  const slice = pastedSlice(at, value, DOCUMENT)
  assert.ok(slice, `nothing to paste from ${JSON.stringify(value)}`)
  return at.apply(at.tr.replaceSelection(slice))
}

const GLUED = ['abc', 'f00', 'Deadline', 'xyz', 'текст', 'Текст со ссылкой', '2026', 'snake_case']

const SCENARIOS = {
  'a-pill-right-before-a-word-prints-as-a-word-of-its-own'() {
    for (const code of [A, B, T]) {
      for (const word of GLUED) {
        const printed = docToMarkdown(paragraphOf(pill(code), text(word)))
        assert.equal(printed, `${code} ${word}`, `${code} + ${word}`)
        assert.deepEqual(codesIn(printed), [code], printed)
        assert.deepEqual(inlines(markdownToDoc(printed, DOCUMENT)), [pill(code), text(` ${word}`)], printed)
      }
    }
  },

  // A code has no boundary on its left: a word glued before it reads back as the same word and the
  // same pill, and such a text is not rewritten.
  'a-word-glued-before-a-pill-is-left-as-written'() {
    for (const word of GLUED) {
      const printed = docToMarkdown(paragraphOf(text(word), pill(B)))
      assert.equal(printed, `${word}${B}`)
      assert.deepEqual(inlines(markdownToDoc(printed, DOCUMENT)), [text(word), pill(B)], printed)
    }
    assert.equal(throughTheEditor(`Код, приклеенный к слову: SUB${T}.`), `Код, приклеенный к слову: SUB${T}.`)
  },

  'two-pills-side-by-side-keep-both-codes'() {
    // FILE@ and CODEX@ begin with hex letters: glued after a code, they ate it.
    for (const [first, second] of [[T, F], [A, C], [B, A]]) {
      const printed = docToMarkdown(paragraphOf(pill(first), pill(second)))
      assert.equal(printed, `${first} ${second}`)
      assert.deepEqual(codesIn(printed), [first, second])
    }
  },

  'punctuation-and-blanks-next-to-a-pill-print-the-same-bytes'() {
    const texts = [
      `${B}.`, `(${B})`, `${B}, ${A}; ${T}!`, `«${B}»`, `${B}-ой`, `см. ${T}: готово`,
      `${B} текст`, `${A}\n\nТекст`, `${A}  \n${B}`, `${T}/${F}`, `№${T}`, `${B}…`,
    ]
    for (const [name, features] of Object.entries(FIELDS)) {
      for (const value of texts) assert.equal(throughTheEditor(value, features), value, `${name}: ${JSON.stringify(value)}`)
    }
  },

  'a-code-glued-before-is-separated-on-the-next-save'() {
    // The body the paste left behind (JOURNAL@5CED8D5129).
    const once = throughTheEditor(`${B.slice(0, 6)}57BC79FAA6Текст со ссылкой`)
    assert.equal(once, 'IMAGE@57BC79FAA6 Текст со ссылкой')
    assert.equal(throughTheEditor(once), once)
  },

  'a-pill-inside-a-mark-stays-inside-its-run'() {
    const texts = [
      `**жирный ${T} рядом**`,
      `*курсив ${A} рядом*`,
      `~~зачёркнуто ${F} тут~~`,
      `***оба ${B} сразу***`,
      `**${A}**`,
      `**${A} ${B}**`,
      `Текст **жирный ${T}** и дальше`,
      `**жирный *курсив ${T} внутри* жирный**`,
      `*курсив **жирный ${T}** курсив*`,
      `**жирный *курсив* жирный**`,
      `- пункт **с ${T} кодом**\n- второй`,
      `## Заголовок **с ${T}**`,
    ]
    for (const [name, features] of Object.entries(FIELDS)) {
      for (const value of texts) {
        if (value.startsWith('##') && !features.has('heading')) continue
        const once = throughTheEditor(value, features)
        assert.equal(once, value, `${name}: ${JSON.stringify(value)}`)
        assert.equal(throughTheEditor(once, features), once, `${name}: second pass`)
      }
    }
  },

  // A mark that outlives another opens first: closed and reopened next to a blank, its delimiter
  // opens nothing and is escaped on the next save for good.
  'nested-marks-of-different-length-print-the-same-bytes'() {
    const texts = [
      '***a** b*', '***a* b**', '~~**a** b~~', '~~*a* b~~', '*~~a~~ b*',
      `***${T}** b*`, `***${T}**, b*`, `*a **${T}** b*`,
      '**[ссылка](https://example.com) текст**', '**a `код` b**',
      '**a  \nb**', `**${T}  \nтекст**`,
    ]
    for (const value of texts) {
      const once = throughTheEditor(value)
      assert.equal(once, value, JSON.stringify(value))
      assert.equal(throughTheEditor(once), once, `second pass of ${JSON.stringify(value)}`)
    }
    assert.equal(throughTheEditor(`_**${T}** b_`), `***${T}** b*`)
  },

  'blanks-at-the-edges-of-marked-nodes-stay-outside-the-delimiters'() {
    const italic = { type: 'italic' }
    const strike = { type: 'strike' }
    const cases = [
      [[text('a', [bold, italic]), text(' b', [italic])], '***a** b*'],
      [[text('x', [bold]), text(' ', [bold, italic]), text('y', [italic])], '**x** *y*'],
      [[text('a', [italic]), text(' ', [italic, bold]), text('b', [bold])], '*a* **b**'],
      [[pill(T, [bold, italic]), text(' b', [italic])], `***${T}** b*`],
      // A blank spread over two nodes at the edge of a run leaves it whole.
      [[text('x ', [bold, strike]), text(' ', [strike]), text('y')], '**~~x~~**  y'],
      [[text('x ', [bold, italic]), text(' ', [bold]), text('y')], '***x***  y'],
    ]
    for (const [content, expected] of cases) {
      const printed = docToMarkdown(paragraphOf(...content))
      assert.equal(printed, expected, JSON.stringify(content))
      assert.equal(throughTheEditor(printed), printed)
    }
    // Crossing runs cannot nest; whatever the printer does, the second pass equals the first and
    // the words stay the words.
    const crossing = docToMarkdown(paragraphOf(text('a ', [strike]), text('b', [strike, bold]), text(' c', [bold])))
    assert.equal(throughTheEditor(crossing), crossing, crossing)
    assert.equal(loaded(crossing).doc.textContent, 'a b c', crossing)
  },

  // Markup between a code and a word already ends the code; such a text keeps its bytes.
  'a-delimiter-between-a-code-and-a-word-is-boundary-enough'() {
    const texts = [
      `${T}**жирный**`, `${T}\`код\``, `${T}[ссылка](https://example.com)`, `**${T}**слово`,
      `~~${T}~~x`, `${T}*x*`,
    ]
    for (const value of texts) assert.equal(throughTheEditor(value), value, JSON.stringify(value))
  },

  'parsing-gives-the-pill-the-marks-around-it'() {
    const doc = markdownToDoc(`**жирный ${T} рядом**`, DOCUMENT)
    assert.deepEqual(inlines(doc), [text('жирный ', [bold]), pill(T, [bold]), text(' рядом', [bold])])
    // A code in backticks is still the pill — inside the run, without the code mark.
    const spanned = markdownToDoc(`**жирный \`${T}\` рядом**`, DOCUMENT)
    assert.deepEqual(inlines(spanned), [text('жирный ', [bold]), pill(T, [bold]), text(' рядом', [bold])])
    // In a link label a code is text, in backticks too: a pill there would put a link in a link.
    const link = { type: 'link', attrs: { href: 'https://example.com' } }
    const labelled = markdownToDoc(`[\`${T}\`](https://example.com)`, DOCUMENT)
    assert.deepEqual(inlines(labelled), [text(T, [link, { type: 'code' }])])
    assert.equal(throughTheEditor(`[\`${T}\`](https://example.com)`), `[\`${T}\`](https://example.com)`)
  },

  'a-field-without-the-mark-or-without-pills-keeps-the-rest'() {
    // No bold here: the pill loses the mark with its neighbours.
    const plain = resolveFeatures('full', ['entityRef'])
    assert.deepEqual(inlines(markdownToDoc(`**жирный ${T} рядом**`, plain)), [text('жирный '), pill(T), text(' рядом')])
    // No pills here: the code stays text, and stays in the bold run.
    const simple = resolveFeatures('simple')
    assert.equal(throughTheEditor(`**жирный ${T} рядом**`, simple), `**жирный ${T} рядом**`)
  },

  'a-body-loaded-and-saved-unedited-keeps-its-bytes'() {
    const body = [
      `Экран: ${A} ${B}`,
      `**жирный ${T} рядом** и *курсив ${F}*.`,
      `- ${C}: правило\n- **${T}**`,
    ].join('\n\n')
    for (const [name, features] of Object.entries(FIELDS)) {
      assert.equal(saved(loaded(body, features)), body, name)
    }
  },

  'an-edit-elsewhere-keeps-the-codes-and-the-marks'() {
    const body = `Первый абзац.\n\n**жирный ${T} рядом** и ${B}.\n\n- ${A} пункт`
    let state = loaded(body)
    state = state.apply(state.tr.insertText(' Дописано.', after(state, 'Первый абзац.')))
    assert.equal(saved(state), `Первый абзац. Дописано.\n\n**жирный ${T} рядом** и ${B}.\n\n- ${A} пункт`)
  },

  'an-edit-inside-the-bold-run-keeps-the-pill-in-it'() {
    let state = loaded(`**жирный ${T} рядом**`)
    state = state.apply(state.tr.insertText(' совсем', after(state, 'рядом')))
    assert.equal(saved(state), `**жирный ${T} рядом совсем**`)
  },

  'text-pasted-after-a-pill-at-the-end-of-a-paragraph-is-not-glued-to-it'() {
    const start = () => loaded(`Скрин: ${A}`)
    const end = (state) => endOfBlock(state, 0)

    // The paste of the finding: a blank line ahead of the text is a new paragraph.
    let state = start()
    state = paste(state, '\n\nТекст со ссылкой', end(state))
    assert.equal(saved(state), `Скрин: ${A}\n\nТекст со ссылкой`)

    // Without a blank the text stays in the paragraph, and the code stays a word of its own.
    for (const word of ['Текст', 'abc', 'xyz', '42']) {
      state = start()
      state = paste(state, word, end(state))
      const printed = saved(state)
      assert.equal(printed, `Скрин: ${A} ${word}`)
      assert.deepEqual(codesIn(printed), [A])
    }

    // A blank at the edge of the pasted text is kept.
    state = start()
    state = paste(state, ' Текст', end(state))
    assert.equal(saved(state), `Скрин: ${A} Текст`)
  },

  'the-edges-of-a-pasted-text-are-kept'() {
    let state = loaded('привет')
    state = paste(state, ' мир', endOfBlock(state, 0))
    assert.equal(saved(state), 'привет мир')

    state = loaded('мир')
    state = paste(state, 'привет ', 1)
    assert.equal(saved(state), 'привет мир')

    state = loaded('ab')
    state = paste(state, '\nx', after(state, 'a'))
    assert.equal(saved(state), 'a xb')

    state = loaded('abcd')
    state = paste(state, 'x\n\n', after(state, 'ab'))
    assert.equal(saved(state), 'abx\n\ncd')
    assert.equal(state.doc.childCount, 2)

    // A blank line at an edge the caret already stands at adds no empty paragraph.
    state = loaded('cd')
    state = paste(state, '\n\nx', 1)
    assert.equal(saved(state), 'xcd')
    assert.equal(state.doc.childCount, 1)

    state = loaded('ab')
    state = paste(state, 'x\n\n', endOfBlock(state, 0))
    assert.equal(state.doc.childCount, 1)
    assert.equal(saved(state), 'abx')

    // In the middle, as before: the pasted paragraphs split the line.
    state = loaded('abcd')
    state = paste(state, 'x\n\ny', after(state, 'ab'))
    assert.equal(saved(state), 'abx\n\nycd')

    // A blank next to a blank or a line break is not doubled.
    state = loaded('a b')
    state = paste(state, ' x ', after(state, 'a '))
    assert.equal(saved(state), 'a x b')
    state = loaded('a  \nb')
    state = paste(state, ' x', after(state, 'a'))
    assert.equal(saved(state), 'a x  \nb')

    // A no-break space is text, not an edge: it is pasted as it is and gets no blank beside it.
    state = loaded('ab')
    state = paste(state, ' x', after(state, 'a'))
    assert.equal(state.doc.textContent, 'a xb')
  },

  // A list item and a table cell are not paragraphs of the document: a blank line there cannot
  // start a paragraph without breaking the list or the table, so it is one blank like any other.
  'a-blank-line-pasted-into-an-item-or-a-cell-keeps-the-list-and-the-table'() {
    let state = loaded('- a\n- b')
    state = paste(state, '\n\nx', after(state, 'a'))
    assert.equal(saved(state), '- a x\n- b')

    state = loaded('| hh | i |\n| --- | --- |\n| ab | c |')
    state = paste(state, '\n\nx', after(state, 'a'))
    assert.equal(saved(state), '| hh | i |\n| --- | --- |\n| a xb | c |')

    state = loaded('| hh | i |\n| --- | --- |\n| ab | c |')
    state = paste(state, '\n\nx', after(state, 'h'))
    assert.equal(saved(state), '| h xh | i |\n| --- | --- |\n| ab | c |')
  },

  'a-pasted-bold-code-is-a-pill-inside-the-run'() {
    let state = loaded('Итог:')
    state = paste(state, ` **жирный ${T} рядом**`, endOfBlock(state, 0))
    assert.equal(saved(state), `Итог: **жирный ${T} рядом**`)
  },
}

const [, , scenario] = process.argv
if (scenario === '--list') {
  console.log(JSON.stringify(Object.keys(SCENARIOS)))
} else {
  assert.ok(scenario in SCENARIOS, `unknown scenario ${scenario}`)
  await SCENARIOS[scenario]()
  console.log('ok')
}
