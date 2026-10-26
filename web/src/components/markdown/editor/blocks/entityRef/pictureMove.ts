// Moving a picture to another place in the text — the edit a drag ends with (`pictureDrag.ts`) and
// the one Alt+←/→ makes on a selected picture — and taking it out of the text, the picture menu's
// delete. The place is either inside a line — next to a word or another picture — or between two
// blocks, where the picture opens a line of its own.
//
// A picture is an `IMAGE@` code in the stored text, and a code reads as one only with a blank or the
// line's edge on both sides: `IMAGE@0123456789` glued to a word is not a code. So the move carries its
// blanks with it. The picture leaves with one blank of its own — the one after it, or the one before
// when it was last — so «A B C» without B reads «A C», not «A  C»; it lands with a blank added on
// whichever side a word or another code would otherwise touch it.
//
// Written over ProseMirror's model with no editor code imported: checked under Node
// (`tests/apps/web_editor_images.mjs`).
import type { Node as ProseMirrorNode, ResolvedPos } from '@tiptap/pm/model'
import { NodeSelection, type EditorState, type Transaction } from '@tiptap/pm/state'
import { inlineChildren, imageRuns, isImageCode } from './imageRuns'

const BLANK = /\s/

function isPicture(node: ProseMirrorNode | null | undefined): node is ProseMirrorNode {
  return !!node && node.type.name === 'entityRef' && isImageCode(String(node.attrs.code ?? ''))
}

/**
 * Whether a neighbour of a place lets a code touch it: none (the line's edge), a line break, or text
 * with a blank on the side facing the place.
 */
function opensOnBlank(node: ProseMirrorNode | null, side: 'before' | 'after'): boolean {
  if (!node || node.type.name === 'hardBreak') return true
  if (!node.isText) return false
  const text = node.text ?? ''
  return BLANK.test(side === 'before' ? text[text.length - 1] : text[0])
}

/**
 * The range the picture at `from` leaves with: itself and one blank beside it — or its whole
 * paragraph when it stood there alone, so the move leaves no empty line behind. Not the document's
 * only block: a document is never left without one.
 */
function leavingRange(doc: ProseMirrorNode, from: number): [number, number] {
  const $at = doc.resolve(from)
  const after = doc.resolve(from + 1).nodeAfter
  const before = $at.nodeBefore
  let range: [number, number] = [from, from + 1]
  if (after?.isText && BLANK.test((after.text ?? '')[0])) range = [from, from + 2]
  else if (before?.isText && BLANK.test((before.text ?? '').slice(-1))) range = [from - 1, from + 1]
  const alone = range[0] === $at.start() && range[1] === $at.end()
  if (alone && $at.depth > 0 && $at.node(-1).childCount > 1) return [$at.before(), $at.after()]
  return range
}

/**
 * Whether a picture may land at `$pos`: in a paragraph's or a list item's text, nowhere else — a
 * heading is a title, a table cell holds a line, and a code block takes no codes at all.
 */
export function takesPicture($pos: ResolvedPos, picture: ProseMirrorNode): boolean {
  const parent = $pos.parent
  if (!parent.inlineContent || parent.type.spec.code) return false
  if (parent.type.name === 'heading' || parent.type.name === 'tableCell') return false
  return parent.canReplaceWith($pos.index(), $pos.index(), picture.type, picture.marks)
}

/**
 * The seam nearest to `pos` a picture may land at: a drop inside a word lands at the word's nearer
 * edge, not between two of its letters.
 */
export function nearestSeam(doc: ProseMirrorNode, pos: number): number {
  const $pos = doc.resolve(pos)
  const offset = $pos.textOffset
  // Between two nodes: already a seam.
  if (offset === 0) return pos
  const text = $pos.parent.child($pos.index()).text ?? ''
  const start = pos - offset
  if (BLANK.test(text[offset - 1]) || BLANK.test(text[offset])) return pos
  let left = offset
  while (left > 0 && !BLANK.test(text[left - 1])) left -= 1
  let right = offset
  while (right < text.length && !BLANK.test(text[right])) right += 1
  return start + (offset - left <= right - offset ? left : right)
}

/** Whether `$pos` is a boundary between blocks where a paragraph of its own may open. */
export function opensLine($pos: ResolvedPos): boolean {
  const paragraph = $pos.doc.type.schema.nodes.paragraph
  if (!paragraph || $pos.parent.inlineContent) return false
  return $pos.parent.canReplaceWith($pos.index(), $pos.index(), paragraph)
}

/**
 * The move of the picture at `from` to the place `to` (both positions in `state.doc`), the moved
 * picture selected after it; `null` — the text would not change, or the place takes no picture.
 *
 * `to` inside a line of text puts the picture into that line; `to` at a boundary between blocks
 * puts it on a line of its own — a new paragraph there.
 */
export function movePicture(state: EditorState, from: number, to: number): Transaction | null {
  const picture = state.doc.nodeAt(from)
  if (!isPicture(picture)) return null
  const $to = state.doc.resolve(to)
  const ownLine = opensLine($to)
  if (!ownLine && !takesPicture($to, picture)) return null

  const [leaveFrom, leaveTo] = leavingRange(state.doc, from)
  // A place inside what leaves is where the picture already stands.
  if (to > leaveFrom && to < leaveTo) return null

  const tr = state.tr.delete(leaveFrom, leaveTo)
  const landed = tr.mapping.map(to)
  const { schema } = state
  if (ownLine) {
    tr.insert(landed, schema.nodes.paragraph.create(null, picture))
    if (tr.doc.eq(state.doc)) return null
    return tr.setSelection(NodeSelection.create(tr.doc, landed + 1))
  }

  const $landed = tr.doc.resolve(landed)
  const parts: ProseMirrorNode[] = []
  if (!opensOnBlank($landed.nodeBefore, 'before')) parts.push(schema.text(' ', $landed.nodeBefore?.marks))
  parts.push(picture)
  if (!opensOnBlank($landed.nodeAfter, 'after')) parts.push(schema.text(' ', $landed.nodeAfter?.marks))
  tr.insert(landed, parts)
  if (tr.doc.eq(state.doc)) return null

  const at = landed + (parts[0] === picture ? 0 : 1)
  return tr.setSelection(NodeSelection.create(tr.doc, at))
}

/**
 * The picture at `pos` taken out of the text — the picture menu's «Удалить из текста». It leaves as a
 * moved one does: with one blank of its own, or with its line when it stood there alone. The file
 * stays with its holder; only the text stops showing it.
 */
export function removePicture(state: EditorState, pos: number): Transaction | null {
  if (!isPicture(state.doc.nodeAt(pos))) return null
  const [from, to] = leavingRange(state.doc, pos)
  return state.tr.delete(from, to)
}

/** Where a selected picture stands in its gallery: its place and the gallery's size, counted from 1. */
export interface GalleryPlace {
  position: number
  total: number
}

/**
 * Alt+←/→ on a selected picture: one place back or forward in its gallery, the gallery's order and
 * nothing else changed. `null` — no picture is selected, or it already stands at that end.
 */
export function stepPicture(
  state: EditorState,
  direction: -1 | 1,
): { tr: Transaction; place: GalleryPlace } | null {
  const { selection } = state
  if (!(selection instanceof NodeSelection) || !isPicture(selection.node)) return null
  const $at = state.doc.resolve(selection.from)
  const block = $at.parent
  const index = $at.index()
  const run = imageRuns(inlineChildren(block)).find((one) => one.indexes.includes(index))
  if (!run) return null
  const at = run.indexes.indexOf(index)
  const next = at + direction
  if (next < 0 || next >= run.indexes.length) return null

  const start = $at.start()
  const offsetOf = (child: number): number => {
    let offset = 0
    for (let i = 0; i < child; i += 1) offset += block.child(i).nodeSize
    return start + offset
  }
  const neighbour = offsetOf(run.indexes[next])
  // Back — ahead of the neighbour; forward — right after it, ahead of its blank.
  const to = direction === -1 ? neighbour : neighbour + 1
  const tr = movePicture(state, selection.from, to)
  return tr ? { tr, place: { position: next + 1, total: run.indexes.length } } : null
}
