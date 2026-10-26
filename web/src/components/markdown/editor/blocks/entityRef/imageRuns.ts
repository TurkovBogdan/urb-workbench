// Which pictures of a paragraph are one gallery — the renderer's rule (`image_galleries` in
// `renderer/render.ts`) read off the editor's document: `IMAGE@` codes in a row, apart only by
// blanks or a line break inside the paragraph. A paragraph break ends a gallery because a gallery
// never leaves its paragraph.
//
// Written over the plain shape both a ProseMirror node's children and the bridge's JSON share, with
// no editor code imported: the rule is checked under Node against the renderer's (`tests/apps`).
import type { Node as ProseMirrorNode } from '@tiptap/pm/model'
import { IMAGE_TYPE } from '../../../shared/contracts'
import { pictureClasses, rowBreakClasses, rowStarts } from '../../../shared/pictures'

/** An inline child as the rule sees it: its node type, its text, the code of a reference. */
export interface InlineLike {
  type: string
  text?: string
  code?: string
}

/** One gallery: the codes in order, and the index of each among the paragraph's children. */
export interface ImageRun {
  codes: string[]
  indexes: number[]
}

export function isImageCode(code: string): boolean {
  return code.split('@')[0].toUpperCase() === IMAGE_TYPE
}

function isImage(child: InlineLike): boolean {
  return child.type === 'entityRef' && isImageCode(child.code ?? '')
}

function isGap(child: InlineLike): boolean {
  return (child.type === 'text' && !(child.text ?? '').trim()) || child.type === 'hardBreak'
}

/** A block's inline children in the shape the rule reads. */
export function inlineChildren(block: ProseMirrorNode): InlineLike[] {
  const children: InlineLike[] = []
  block.forEach((child) => {
    children.push({ type: child.type.name, text: child.text, code: String(child.attrs.code ?? '') })
  })
  return children
}

/** The galleries of one paragraph, a lone picture included as a run of one. */
export function imageRuns(children: readonly InlineLike[]): ImageRun[] {
  const runs: ImageRun[] = []
  let open: ImageRun | null = null
  children.forEach((child, index) => {
    if (isImage(child)) {
      if (!open) {
        open = { codes: [], indexes: [] }
        runs.push(open)
      }
      open.codes.push(child.code ?? '')
      open.indexes.push(index)
    } else if (!isGap(child)) {
      open = null
    }
  })
  return runs
}

/** Spacing the layout hides: a child, and for text the characters `[from, to)` of it. */
export interface PictureGap {
  index: number
  from: number
  to: number
}

/** A line break around a run: ahead of the child `index`'s character `offset`. */
export interface PictureBreak {
  index: number
  offset: number
  /** Ahead of the run (`true`) or after it. */
  before: boolean
  /** The run is one picture — which stays in the line when its file turns out not to be one. */
  single: boolean
}

/**
 * How a paragraph's pictures stand in it — the viewer's layout read off the editor's document,
 * where no wrapper can hold a gallery: a run breaks out of the text line onto rows of its own, and
 * the text after it continues on a new line.
 *
 * - `pictures` — each picture with the classes of its gallery (`pictureClasses`): the column count
 *   the stylesheet lays the row out by;
 * - `spaces` — the first blank after a picture of a run, between two pictures or ahead of the text
 *   after the run: a real space, drawn as wide as the gallery's gap, so the caret stands after the
 *   picture as it does after a word;
 * - `gaps` — the rest of the spacing around a run: the blanks after that first one, a line break
 *   between its pictures, the blank a line opens with before it. They would stand as spaces in the
 *   row, so they are drawn at no width;
 * - `lineStarts` — the pictures that open a line, with no text ahead of them to hold the caret;
 * - `lineEnds` — the pictures that close a line — the paragraph or a hard break comes next —, with
 *   no text after them to hold the caret;
 * - `breaks` — where the line breaks: ahead of a run that follows text, after a run that text
 *   follows. A hard break already breaks the line and needs none;
 * - `rows` — where a row of a gallery starts, ahead of the picture `index`, with the classes that
 *   name the widths it starts a row in (`rowStarts`, from the pictures' proportions as `ratioOf`
 *   knows them): the viewer's gallery carries the same breaks.
 */
export function pictureLayout(children: readonly InlineLike[], ratioOf: (code: string) => number = () => 4 / 3): {
  pictures: { index: number; classes: string[] }[]
  spaces: PictureGap[]
  gaps: PictureGap[]
  lineStarts: number[]
  lineEnds: number[]
  breaks: PictureBreak[]
  rows: { index: number; classes: string }[]
  runs: number[][]
} {
  const pictures: { index: number; classes: string[] }[] = []
  const spaces: PictureGap[] = []
  const gaps: PictureGap[] = []
  const lineStarts: number[] = []
  const lineEnds: number[] = []
  const breaks: PictureBreak[] = []
  const rows: { index: number; classes: string }[] = []
  const runs: number[][] = []
  const isLineBreak = (child: InlineLike | undefined): boolean => child?.type === 'hardBreak'
  const textOf = (child: InlineLike | undefined): string => (child?.type === 'text' ? child.text ?? '' : '')
  const wholeGap = (index: number): PictureGap => ({ index, from: 0, to: textOf(children[index]).length })
  // The first blank after a picture is its space, the rest are drawn at no width.
  const spaceAfterPicture = (index: number, to: number): void => {
    spaces.push({ index, from: 0, to: 1 })
    if (to > 1) gaps.push({ index, from: 1, to })
  }

  for (const run of imageRuns(children)) {
    const first = run.indexes[0]
    const last = run.indexes[run.indexes.length - 1]
    const single = run.indexes.length === 1
    const classes = pictureClasses(run.indexes.length)
    for (const index of run.indexes) {
      pictures.push({ index, classes })
      const next = children[index + 1]
      if (!next || isLineBreak(next)) lineEnds.push(index)
    }
    runs.push(run.indexes)
    for (const start of rowStarts(run.codes.map(ratioOf))) {
      rows.push({ index: run.indexes[start.index], classes: rowBreakClasses(start.modes) })
    }
    for (let index = first + 1; index < last; index += 1) {
      if (run.indexes.includes(index)) continue
      const blank = wholeGap(index)
      if (children[index].type === 'text') spaceAfterPicture(index, blank.to)
      else gaps.push(blank)
    }

    const before = children[first - 1]
    if (!before || isLineBreak(before)) {
      lineStarts.push(first)
    } else {
      const opensLine = first - 1 === 0 || isLineBreak(children[first - 2])
      if (before.type === 'text' && !textOf(before).trim() && opensLine) gaps.push(wholeGap(first - 1))
      else breaks.push({ index: first, offset: 0, before: true, single })
    }

    const after = children[last + 1]
    if (!after || isLineBreak(after)) continue
    if (after.type !== 'text') {
      breaks.push({ index: last + 1, offset: 0, before: false, single })
      continue
    }
    const text = textOf(after)
    const blank = text.length - text.trimStart().length
    if (blank) spaceAfterPicture(last + 1, blank)
    const closesLine = blank === text.length && (!children[last + 2] || isLineBreak(children[last + 2]))
    if (!closesLine) breaks.push({ index: last + 1, offset: blank, before: false, single })
  }
  return { pictures, spaces, gaps, lineStarts, lineEnds, breaks, rows, runs }
}
