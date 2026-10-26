// Scenarios for `IMAGE@` pictures in the editor, executed under Node against the real files — see
// `test_web_editor_images.py`. Run as `node … web_editor_images.mjs <scenario>`; a failed `assert`
// exits non-zero with the reason on stderr.
//
// A picture in the editor is the same `entityRef` node as a pill, drawn otherwise: what is checked
// here is that a field's text passes through the editor's bridge unchanged with pictures in it,
// and that the editor groups pictures into galleries exactly as the viewer does. The sanitiser is
// replaced by a pass-through (it needs a DOM, and the grouping happens before it).

import assert from 'node:assert/strict'
import { register } from 'node:module'

const WEB_SRC = new URL('../../web/src/', import.meta.url)

const FAKES = {
  dompurify: 'export default { sanitize: (html) => html }',
}

register(
  'data:text/javascript,' +
    encodeURIComponent(`
      const WEB_SRC = ${JSON.stringify(WEB_SRC.href)}
      const FAKES = ${JSON.stringify(FAKES)}
      export async function resolve(specifier, context, next) {
        if (specifier in FAKES) {
          return { url: 'data:text/javascript,' + encodeURIComponent(FAKES[specifier]), shortCircuit: true }
        }
        if (specifier.startsWith('@/')) return next(WEB_SRC + specifier.slice(2) + '.ts', context)
        // The sources import their neighbours without the extension, as Vite allows.
        if (specifier.startsWith('.') && !/\\.[a-z]+$/.test(specifier) && context.parentURL?.startsWith(WEB_SRC)) {
          return next(specifier + '.ts', context)
        }
        return next(specifier, context)
      }
    `),
)

const src = (path) => new URL(path, WEB_SRC).href

const { markdownToDoc, docToMarkdown } = await import(src('components/markdown/editor/bridge/index.ts'))
const { imageRuns, pictureLayout } = await import(src('components/markdown/editor/blocks/entityRef/imageRuns.ts'))
const { galleryLayout, galleryRowCount, galleryRows, pictureClasses, rowStarts, wideRows } = await import(
  src('components/markdown/shared/pictures.ts')
)

/** A row's height at the nominal width the rows are balanced on (560 px, gap 8). */
const rowHeightAt = (ratios, row) => (560 - row.length * 8) / row.reduce((total, index) => total + ratios[index], 0)
const { movePicture, nearestSeam, removePicture, stepPicture } = await import(src('components/markdown/editor/blocks/entityRef/pictureMove.ts'))
const { renderMarkdown } = await import(src('components/markdown/renderer/render.ts'))
const { resolveFeatures } = await import(src('components/markdown/editor/modes.ts'))
const { TASK_BRIEF_FEATURES, TASK_DOCUMENT_FEATURES } = await import(src('features/tasks/editor.ts'))
const { CODEX_DOCUMENT_FEATURES } = await import(src('features/codex/editor.ts'))

// ProseMirror itself, the very files the editor's modules import: a selection made here must be the
// class `pictureMove.ts` checks against.
const PM = new URL('../../web/node_modules/@tiptap/pm/dist/', import.meta.url)
const { Schema, Node: PMNode } = await import(new URL('model/index.js', PM).href)
const { EditorState, NodeSelection } = await import(new URL('state/index.js', PM).href)

/** The nodes the bridge writes for the texts below — the editor's names, nothing more. */
const SCHEMA = new Schema({
  nodes: {
    doc: { content: 'block+' },
    paragraph: { group: 'block', content: 'inline*' },
    heading: { group: 'block', content: 'inline*', attrs: { level: { default: 1 } } },
    text: { group: 'inline' },
    hardBreak: { group: 'inline', inline: true },
    entityRef: { group: 'inline', inline: true, atom: true, attrs: { code: { default: '' } } },
  },
  marks: { bold: {} },
})

/** A field's text as the editor holds it. */
function stateOf(text) {
  return EditorState.create({ doc: PMNode.fromJSON(SCHEMA, markdownToDoc(text, resolveFeatures('full', TASK_DOCUMENT_FEATURES))) })
}

/** The text a field would store after the edit. */
const stored = (state) => docToMarkdown(state.doc.toJSON())

/** Positions of the `n`-th occurrence of a code, and of the place right after a piece of text. */
function pictureAt(state, code, n = 0) {
  const found = []
  state.doc.descendants((node, pos) => {
    if (node.type.name === 'entityRef' && node.attrs.code === code) found.push(pos)
  })
  return found[n]
}

function after(state, piece) {
  let at = null
  state.doc.descendants((node, pos) => {
    if (at === null && node.isText && node.text.includes(piece)) at = pos + node.text.indexOf(piece) + piece.length
  })
  return at
}

const A = 'IMAGE@0123456789'
const B = 'IMAGE@ABCDEF0123'
const C = 'IMAGE@1111111111'
const D = 'IMAGE@2222222222'

const FIELDS = {
  TASK_DOCUMENT_FEATURES,
  TASK_BRIEF_FEATURES,
  CODEX_DOCUMENT_FEATURES,
}

/** The text after a load and a save with nothing edited. */
function throughTheEditor(text, features) {
  return docToMarkdown(markdownToDoc(text, resolveFeatures('full', features)))
}

/** Every inline child of the document's text blocks, flattened. */
function inlines(doc) {
  return (doc.content ?? []).flatMap((block) => block.content ?? [])
}

const INLINE = new Set(['text', 'entityRef', 'hardBreak'])

/** Every block holding inline content — a paragraph, a list item, a table cell — in order. */
function textBlocks(node) {
  const children = node.content ?? []
  if (children.some((child) => INLINE.has(child.type))) return [node]
  return children.flatMap(textBlocks)
}

/** The galleries the editor sees, text block by text block: the codes of each run. */
function editorGalleries(text) {
  return textBlocks(markdownToDoc(text)).flatMap((block) =>
    imageRuns(block.content.map((child) => ({ type: child.type, text: child.text, code: child.attrs?.code })))
      .map((run) => run.codes),
  )
}

const PICTURE = '<span class="md-image[^"]*"><a[^>]*data-ref="([^"]+)"><span class="md-ref-label">[^<]*</span></a></span>'
const ROW_BREAK = '(?:<span class="md-row-break[^"]*"></span>)?'
const GALLERY = new RegExp(`<span class="md-gallery[^"]*">((?:${ROW_BREAK}${PICTURE})+)</span>`, 'g')

/** The galleries the viewer draws: the codes of each `span.md-gallery`, in order. */
function viewerGalleries(text) {
  const { html } = renderMarkdown(text, { breaks: false, allowImages: false })
  return [...html.matchAll(GALLERY)].map((gallery) =>
    [...gallery[1].matchAll(new RegExp(PICTURE, 'g'))].map((picture) => picture[1]),
  )
}

const GROUPINGS = {
  'two in a row and a third after a line break': `${A} ${B}\n${C}`,
  'a blank line ends a gallery': `${A} ${B}\n\n${C}`,
  'a word between makes two': `${A} между ${B}`,
  'a hard break keeps one gallery': `${A}  \n${B}`,
  'text around one gallery': `Экраны: ${A} ${B} — до и после.`,
  'a code inside a link stays text': `[${A}](https://example.com) ${B}`,
  'a file between pictures splits them': `${A} FILE@3333333333 ${B}`,
  'pictures in a list item and a table cell': `- ${A} ${B}\n\n| a |\n| - |\n| ${C} ${D} |`,
}

const scenarios = {
  a_field_with_pictures_saves_the_same_bytes_it_loaded() {
    const texts = [
      `Экраны входа: ${A} ${B} ${C}\n\nОдин крупно:\n\n${D}`,
      `Итог:\n\n- до: ${A}\n- после: ${B}\n\nФайл FILE@3333333333 и задача TASK@4444444444.`,
      `${A}\n\nIMAGE@5555555555 — картинка, которой нет; ${B} в конце строки ${C}`,
      `**жирный** ${A} и *курсив* ${B}`,
    ]
    for (const [name, features] of Object.entries(FIELDS)) {
      for (const text of texts) {
        const once = throughTheEditor(text, features)
        assert.equal(once, text, `${name}: ${JSON.stringify(text)}`)
        assert.equal(throughTheEditor(once, features), once, `${name}: second pass`)
      }
    }
  },

  every_task_and_codex_field_draws_pictures() {
    for (const [name, features] of Object.entries(FIELDS)) {
      const set = resolveFeatures('full', features)
      assert.ok(set.has('image'), `${name} has pictures`)
      assert.ok(set.has('entityRef'), `${name} has the reference a picture is drawn from`)
    }
  },

  a_picture_code_is_a_reference_node_not_text() {
    const doc = markdownToDoc(`Смотри ${A} и ${B}.`, resolveFeatures('full', TASK_DOCUMENT_FEATURES))
    const refs = inlines(doc).filter((node) => node.type === 'entityRef').map((node) => node.attrs.code)
    assert.deepEqual(refs, [A, B])
  },

  a_lower_case_picture_code_is_stored_upper_case_as_any_pill() {
    assert.equal(throughTheEditor(A.toLowerCase(), TASK_DOCUMENT_FEATURES), A)
  },

  the_editor_groups_pictures_as_the_viewer_does() {
    for (const [name, text] of Object.entries(GROUPINGS)) {
      assert.deepEqual(editorGalleries(text), viewerGalleries(text), name)
    }
  },

  the_count_gives_the_number_of_rows() {
    const rows = Array.from({ length: 16 }, (_, n) => galleryRowCount(n + 1))
    assert.deepEqual(rows, [1, 1, 1, 2, 2, 2, 2, 2, 3, 3, 3, 3, 4, 4, 4, 4])
    assert.deepEqual(pictureClasses(1), ['md-image--cols-1', 'md-image--single'])
    assert.deepEqual(pictureClasses(4), ['md-image--cols-2'])
    assert.deepEqual(pictureClasses(10), ['md-image--cols-4'])
  },

  pictures_of_one_shape_split_by_the_count_with_the_short_row_last() {
    const neutral = (count) => wideRows(Array(count).fill(4 / 3)).map((row) => row.length).join('+')
    const shapes = Array.from({ length: 12 }, (_, n) => neutral(n + 1))
    assert.deepEqual(shapes, ['1', '2', '3', '2+2', '3+2', '3+3', '4+3', '4+4', '3+3+3', '4+3+3', '4+4+3', '4+4+4'])
  },

  rows_by_width() {
    const sizes = (ratios, mode) => galleryRows(ratios, mode).map((row) => row.length).join('+')
    const seven = Array(7).fill(4 / 3)
    assert.equal(sizes(seven, 'mid'), '2+2+2+1', 'a narrow body: two in a row')
    assert.equal(sizes(seven.slice(0, 3), 'narrow'), '1+1+1', 'a very narrow one: one')
    assert.deepEqual(rowStarts(seven).find((start) => start.index === 4).modes, ['wide', 'mid', 'narrow'])
  },

  mixed_proportions_make_no_strip_and_no_orphan() {
    // The person's check set: 16:9, 9:16, 1:1, 4:1, a 32×32 icon, 3:4, 21:9, 1:2, 4:3, 2:1.
    const set = [16 / 9, 9 / 16, 1, 4, 1, 3 / 4, 21 / 9, 1 / 2, 4 / 3, 2]
    for (let count = 2; count <= set.length; count += 1) {
      const ratios = set.slice(0, count)
      const rows = wideRows(ratios)
      const heights = rows.map((row) => rowHeightAt(ratios, row))
      if (count >= 4) assert.ok(Math.min(...heights) >= 90, `${count}: no strip — ${heights.map(Math.round)}`)
      if (count >= 5) assert.ok(rows.every((row) => row.length > 1 || ratios[row[0]] >= 2), `${count}: a lone picture fills its row — ${rows.map((r) => r.length)}`)
      assert.deepEqual(rows.flat(), ratios.map((_, n) => n), `${count}: order kept`)
    }
  },

  one_shape_sets_stay_even() {
    const portraits = wideRows(Array(7).fill(9 / 16))
    assert.equal(portraits.map((row) => row.length).join('+'), '4+3')
    const panoramas = wideRows(Array(6).fill(4))
    assert.ok(panoramas.length > 2, 'panoramas take more rows than the count gives')
    for (const row of panoramas) assert.ok(rowHeightAt(Array(6).fill(4), row) >= 90)
  },

  a_justified_row_shares_one_height() {
    const ratios = [16 / 9, 9 / 16, 1, 4, 16 / 9, 1, 3 / 4, 1, 16 / 9, 1]
    const layout = galleryLayout(ratios)
    for (const row of galleryRows(ratios, 'wide')) {
      const sum = row.reduce((total, index) => total + ratios[index], 0)
      for (const index of row) {
        assert.equal(layout[index]['--s-wide'], sum.toFixed(4))
        assert.equal(layout[index]['--k-wide'], String(row.length))
      }
    }
    const three = galleryLayout([16 / 9, 9 / 16, 1])
    assert.deepEqual(
      [three[2]['--k-mid'], three[2]['--s-mid']],
      ['2', (16 / 9 + 9 / 16).toFixed(4)],
      'a narrow body cuts 3 into 2+1: the one is as tall as the two',
    )
  },

  both_zones_break_the_rows_at_the_same_pictures() {
    const ratios = [16 / 9, 9 / 16, 1, 4, 1, 3 / 4, 21 / 9]
    const codes = ratios.map((_, n) => `IMAGE@${String(n).padStart(10, '0')}`)
    const doc = markdownToDoc(codes.join(' '))
    const children = doc.content[0].content.map((child) => ({ type: child.type, text: child.text, code: child.attrs?.code }))
    const ratioOf = (code) => ratios[codes.indexOf(code)]
    const editor = pictureLayout(children, ratioOf).rows.map((row) => `${children[row.index].code} ${row.classes}`)
    const viewer = rowStarts(ratios).map(({ index, modes }) => `${codes[index]} md-row-break ${modes.map((mode) => `md-row-break--${mode}`).join(' ')}`)
    assert.deepEqual(editor, viewer)
  },

  both_zones_give_every_picture_of_a_gallery_its_column_class() {
    for (let count = 1; count <= 10; count += 1) {
      const codes = Array.from({ length: count }, (_, n) => `IMAGE@${String(n).padStart(10, '0')}`)
      const text = `Текст до: ${codes.join(' ')} и после.`
      const { html } = renderMarkdown(text, { breaks: false, allowImages: false })
      const viewer = [...html.matchAll(/<span class="md-image ([^"]+)">/g)].map((match) => match[1])
      const doc = markdownToDoc(text)
      const paragraph = doc.content[0].content.map((child) => ({ type: child.type, text: child.text, code: child.attrs?.code }))
      const editor = pictureLayout(paragraph).pictures.map((picture) => picture.classes.join(' '))
      assert.deepEqual(viewer, Array(count).fill(pictureClasses(count).join(' ')), `viewer, ${count}`)
      assert.deepEqual(editor, viewer, `editor, ${count}`)
    }
  },

  the_editor_breaks_the_line_around_a_run_and_keeps_a_space_after_each_picture() {
    const children = (text) =>
      markdownToDoc(text).content[0].content.map((child) => ({ type: child.type, text: child.text, code: child.attrs?.code }))

    // "Галерея: " A " " B " и после."
    const mixed = pictureLayout(children(`Галерея: ${A} ${B} и после.`))
    assert.deepEqual(mixed.breaks, [
      { index: 1, offset: 0, before: true, single: false },
      { index: 4, offset: 1, before: false, single: false },
    ])
    assert.deepEqual(mixed.spaces, [{ index: 2, from: 0, to: 1 }, { index: 4, from: 0, to: 1 }], 'the caret stands after each picture')
    assert.deepEqual([mixed.gaps, mixed.lineStarts], [[], []], 'text ahead of the run holds the caret')

    const alone = pictureLayout(children(`${A} ${B}`))
    assert.deepEqual([alone.breaks, alone.spaces, alone.gaps], [[], [{ index: 1, from: 0, to: 1 }], []], 'a paragraph of pictures only')
    assert.deepEqual(alone.lineStarts, [0], 'a picture opening the paragraph has nothing ahead to hold the caret')
    assert.deepEqual(alone.lineEnds, [2], 'a picture closing the paragraph has nothing after it to hold the caret')
    assert.deepEqual(mixed.lineEnds, [], 'text after the run holds the caret')

    // Only the first blank is the space: the rest would widen the gap and push a picture off its row.
    const wide = pictureLayout(children(`${A}   ${B}   и после.`))
    assert.deepEqual(wide.spaces, [{ index: 1, from: 0, to: 1 }, { index: 3, from: 0, to: 1 }])
    assert.deepEqual(wide.gaps, [{ index: 1, from: 1, to: 3 }, { index: 3, from: 1, to: 3 }])

    const placeholder = pictureLayout(children(`Откреплён: ${C}, и FILE@3333333333 рядом.`))
    assert.deepEqual(placeholder.breaks.map((spot) => [spot.index, spot.offset, spot.before, spot.single]), [
      [1, 0, true, true],
      [2, 0, false, true],
    ], 'a punctuation mark after the picture starts the next line')

    const hard = pictureLayout(children(`До:  \n${A}  \n${B}`))
    assert.deepEqual(hard.breaks, [], 'hard breaks already break the line')
    assert.deepEqual(hard.pictures.map((picture) => picture.classes), [pictureClasses(2), pictureClasses(2)])
    assert.deepEqual(hard.spaces, [], 'a hard break between pictures is no space')
    assert.deepEqual(hard.lineStarts, [2], 'a picture after a hard break opens its line')
    assert.deepEqual(hard.lineEnds, [2, 4], 'a picture before a hard break closes its line, as the last one does')
  },

  a_dragged_picture_lands_with_its_blanks_and_leaves_none_behind() {
    const move = (text, code, to) => {
      const state = stateOf(text)
      const tr = movePicture(state, pictureAt(state, code), to(state))
      return tr ? stored(state.apply(tr)) : null
    }
    // Within a gallery: ahead of a picture, after one.
    assert.equal(move(`${A} ${B} ${C}`, A, (s) => pictureAt(s, B) + 1), `${B} ${A} ${C}`)
    assert.equal(move(`${A} ${B} ${C}`, C, (s) => pictureAt(s, A)), `${C} ${A} ${B}`)
    assert.equal(move(`${A} ${B} ${C}`, A, (s) => pictureAt(s, C) + 1), `${B} ${C} ${A}`)
    // Out of the gallery into a line of text, and from the text into a gallery.
    assert.equal(move(`${A} ${B} ${C}\n\nдо и после`, B, (s) => after(s, 'до ')), `${A} ${C}\n\nдо ${B} и после`)
    assert.equal(move(`${A} ${B}\n\nконец`, A, (s) => after(s, 'конец')), `${B}\n\nконец ${A}`)
    assert.equal(move(`${A}\n\nтекст ${B} ${C}`, A, (s) => pictureAt(s, C)), `текст ${B} ${A} ${C}`)
    // A picture glued to nothing: a blank is added on the side a word would touch.
    assert.equal(move(`${A}\n\nслово`, A, (s) => after(s, 'слово') - 'слово'.length), `${A} слово`)
    // Its own place, either side of it or its own blank — nothing changes, so there is no move.
    for (const to of [(s) => pictureAt(s, A), (s) => pictureAt(s, A) + 1, (s) => pictureAt(s, A) + 2]) {
      assert.equal(move(`${A} ${B}`, A, to), null)
    }
    // A picture alone on its line takes the line with it; the document's only line stays.
    assert.equal(move(`${A} ${B}\n\n${C}\n\nтекст`, C, (s) => pictureAt(s, A)), `${C} ${A} ${B}\n\nтекст`)
    {
      const state = stateOf(`текст\n\n${C}\n\nещё`)
      const next = state.apply(movePicture(state, pictureAt(state, C), after(state, 'ещё')))
      assert.equal(next.doc.childCount, 2, 'no empty paragraph is left where the picture stood')
      assert.equal(stored(next), `текст\n\nещё ${C}`)
    }
    // A heading is a title, not a place for a picture.
    assert.equal(move(`# Заголовок\n\n${A} ${B}`, A, (s) => after(s, 'Заголовок')), null)
  },

  a_picture_dropped_between_blocks_opens_a_line_of_its_own() {
    const move = (text, code, to) => {
      const state = stateOf(text)
      const tr = movePicture(state, pictureAt(state, code), to(state))
      return tr ? stored(state.apply(tr)) : null
    }
    // The boundary ahead of the `n`-th block of the document.
    const boundary = (n) => (state) => {
      let pos = 0
      for (let index = 0; index < n; index += 1) pos += state.doc.child(index).nodeSize
      return pos
    }
    assert.equal(move(`${A} ${B}\n\nтекст`, B, boundary(1)), `${A}\n\n${B}\n\nтекст`)
    assert.equal(move(`${A} ${B}\n\nтекст`, A, boundary(2)), `${B}\n\nтекст\n\n${A}`)
    assert.equal(move(`до ${A} после\n\nконец`, A, boundary(0)), `${A}\n\nдо после\n\nконец`)
    // A picture alone on its line, dropped either side of that line: it stays where it is.
    assert.equal(move(`текст\n\n${C}\n\nещё`, C, boundary(1)), null)
    assert.equal(move(`текст\n\n${C}\n\nещё`, C, boundary(2)), null)
    // Moving it a line further takes its own line along: no empty line is left behind.
    assert.equal(move(`текст\n\n${C}\n\nещё`, C, boundary(3)), `текст\n\nещё\n\n${C}`)
    {
      const state = stateOf(`${A} ${B}\n\nтекст`)
      const next = state.apply(movePicture(state, pictureAt(state, B), boundary(1)(state)))
      assert.equal(next.selection.node.attrs.code, B, 'the moved picture stays selected')
    }
  },

  a_picture_removed_from_the_text_leaves_no_blank_or_empty_line() {
    const remove = (text, code) => {
      const state = stateOf(text)
      const tr = removePicture(state, pictureAt(state, code))
      return tr ? stored(state.apply(tr)) : null
    }
    assert.equal(remove(`${A} ${B} ${C}`, B), `${A} ${C}`)
    assert.equal(remove(`${A} ${B} ${C}`, C), `${A} ${B}`)
    assert.equal(remove(`до ${A} после`, A), `до после`)
    assert.equal(remove(`текст\n\n${C}\n\nещё`, C), `текст\n\nещё`)
    const state = stateOf('без картинок FILE@3333333333')
    let pill = null
    state.doc.descendants((node, pos) => { if (node.type.name === 'entityRef') pill = pos })
    assert.equal(removePicture(state, pill), null, 'a pill is not a picture')
  },

  a_drop_inside_a_word_lands_at_its_nearer_edge() {
    const state = stateOf('один слово два')
    const start = after(state, 'один ')
    assert.equal(nearestSeam(state.doc, start + 2), start, 'сл|ово — ahead of the word')
    assert.equal(nearestSeam(state.doc, start + 4), start + 5, 'слов|о — after it')
    assert.equal(nearestSeam(state.doc, start), start, 'a seam stays a seam')
  },

  alt_arrows_move_a_selected_picture_along_its_gallery() {
    const select = (text, code) => {
      const state = stateOf(text)
      return state.apply(state.tr.setSelection(NodeSelection.create(state.doc, pictureAt(state, code))))
    }
    const back = stepPicture(select(`${A} ${B} ${C}`, B), -1)
    assert.deepEqual(back.place, { position: 1, total: 3 })
    const moved = select(`${A} ${B} ${C}`, B).apply(back.tr)
    assert.equal(stored(moved), `${B} ${A} ${C}`)
    assert.equal(moved.selection.node.attrs.code, B, 'the moved picture stays selected')
    const forward = stepPicture(select(`${A} ${B} ${C}`, B), 1)
    assert.equal(stored(select(`${A} ${B} ${C}`, B).apply(forward.tr)), `${A} ${C} ${B}`)
    assert.deepEqual(forward.place, { position: 3, total: 3 })
    assert.equal(stepPicture(select(`${A} ${B} ${C}`, A), -1), null, 'the first goes no further back')
    assert.equal(stepPicture(select(`${A} ${B} ${C}`, C), 1), null, 'the last no further forward')
    assert.equal(stepPicture(select(`${A} текст ${B}`, A), 1), null, 'a word between makes two galleries')
  },

  the_groupings_themselves() {
    assert.deepEqual(editorGalleries(GROUPINGS['two in a row and a third after a line break']), [[A, B, C]])
    assert.deepEqual(editorGalleries(GROUPINGS['a blank line ends a gallery']), [[A, B], [C]])
    assert.deepEqual(editorGalleries(GROUPINGS['a word between makes two']), [[A], [B]])
    assert.deepEqual(editorGalleries(GROUPINGS['a hard break keeps one gallery']), [[A, B]])
    assert.deepEqual(editorGalleries(GROUPINGS['a code inside a link stays text']), [[B]])
    assert.deepEqual(editorGalleries(GROUPINGS['a file between pictures splits them']), [[A], [B]])
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
