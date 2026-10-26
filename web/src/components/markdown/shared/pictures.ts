// What a picture drawn by its code (`IMAGE@`) is showing, and how a gallery of them is laid out —
// one answer for the viewer and the editor, so the same text never reads one way in one zone and
// another in the other.
//
// The preview says whether the file is there and gives its address; whether the file IS a picture
// the preview does not tell — the browser does, by failing to decode it, and such a file stays a
// pill that opens it, like `FILE@`. The failures, and the proportions of the pictures that did
// load, are kept by address for the whole app: the same file is the same everywhere, and a
// re-render (an edit elsewhere in the text, another field with the same code) lays it out at once.
//
// A gallery is laid out in justified rows: the pictures of a row share one height and keep their
// proportions, so the row fills the width. The count gives the number of rows, the proportions
// where they break (`wideRows`), and a narrow body steps down to two and one in a row. The
// proportions come from the loaded pictures (`notePicture`), a neutral 4:3 until then and for
// anything that is not a picture.
import { reactive, ref } from 'vue'
import type { PreviewRecord } from '@/api/lookup'

/** pending — no preview yet; shown — the picture; file — not a picture, a link; missing — gone. */
export type PictureState = 'pending' | 'shown' | 'file' | 'missing'

export const PICTURE_STATES: readonly PictureState[] = ['pending', 'shown', 'file', 'missing']

const notPictures = reactive(new Set<string>())

export function pictureState(record: PreviewRecord | undefined): PictureState {
  if (!record) return 'pending'
  // A failed request says nothing about the file: its pill stays readable rather than a hole.
  if (record.error) return record.error.code === 'failed' ? 'file' : 'missing'
  return notPictures.has(record.link) ? 'file' : 'shown'
}

/** The browser could not show the file at `link` as a picture. */
export function markNotPicture(link: string): void {
  if (link) notPictures.add(link)
}

// ── Proportions ───────────────────────────────────────────────────────────────

/** A slot whose picture is not known yet, or is not a picture at all. */
export const NEUTRAL_RATIO = 4 / 3

// A tall phone screenshot or a panorama would make its row absurd — a row as tall as a page, or a
// strip. The slot keeps within these, and the picture is fitted inside it, not cut.
const RATIO_MIN = 1 / 3
const RATIO_MAX = 4

const ratios = new Map<string, number>()
/**
 * Bumped by every new proportion and every picture changing its state: what lays galleries out
 * lays them out again. The editor's pictures change state in their own views, out of the
 * document's sight (`touchGalleries`).
 */
export const galleryVersion = ref(0)

export function touchGalleries(): void {
  galleryVersion.value += 1
}

/**
 * The picture of `code` (`IMAGE@…`) loaded at this natural size. Kept by code, not by address: the
 * editor lays its rows out from the document, which holds codes. A picture with no size of its
 * own reports zero and keeps the neutral slot.
 */
export function notePicture(code: string, width: number, height: number): void {
  if (!code || !width || !height || ratios.has(code)) return
  ratios.set(code, Math.min(RATIO_MAX, Math.max(RATIO_MIN, width / height)))
  touchGalleries()
}

/**
 * A loaded picture that has no size of its own to stand at: an SVG with only a `viewBox` collapses
 * to nothing alone in its line, while the browser still reports a natural size for it. Such a
 * picture is given a width (`md-image--sizeless` in `document.css`); in a gallery its slot sizes it.
 */
export function isSizeless(image: HTMLImageElement): boolean {
  // The client width leaves the border out: a collapsed picture is still as wide as its border.
  return image.naturalWidth > 2 && image.clientWidth < 2
}

/** The proportion a picture of `code` is laid out by — neutral until it has loaded as a picture. */
export function ratioOf(code: string | null | undefined): number {
  return (code && ratios.get(code)) || NEUTRAL_RATIO
}

// ── The shape of a gallery ───────────────────────────────────────────────────

/**
 * How many rows a gallery of `count` takes at full width: one for two and three, two up to eight,
 * then a row per four begun. Where the rows break is the pictures' business (`wideRows`).
 */
export function galleryRowCount(count: number): number {
  if (count <= 3) return 1
  if (count <= 8) return 2
  return Math.ceil(count / 4)
}

/** The column count a gallery of `count` starts at, before its pictures are measured. */
export function galleryColumns(count: number): number {
  return Math.ceil(count / galleryRowCount(count))
}

// The rows are balanced on a nominal content width: the widths the full layout serves (480 px and
// up) differ little in the proportions they give, and the choice must not jump while a window is
// resized. A row aims at the target height; one under the floor costs much more. A row under the
// strip height even at its best split means the count asked too few rows for these pictures (a
// panorama and a phone shot have to share one): the gallery takes another row, while that helps.
// The measure of a body's text at the default reading size: what a gallery in a task or a note
// gets at full width.
const NOMINAL_WIDTH = 560
const NOMINAL_GAP = 8
const TARGET_ROW = 200
const FLOOR_ROW = 120
const STRIP_ROW = 90
// Past this the exact split costs too much to find on every change; a greedy fill does.
const EXACT_UP_TO = 24

function rowHeight(ratios: readonly number[], from: number, to: number): number {
  let sum = 0
  for (let index = from; index < to; index += 1) sum += ratios[index]
  return (NOMINAL_WIDTH - (to - from) * NOMINAL_GAP) / sum
}

function rowCost(height: number): number {
  const off = height - TARGET_ROW
  const under = Math.max(0, FLOOR_ROW - height)
  return off * off + 20 * under * under
}

const rowsFromStarts = (starts: number[], count: number): number[][] =>
  starts.map((start, n) => Array.from({ length: (starts[n + 1] ?? count) - start }, (_, k) => start + k))

interface Split {
  starts: number[]
  cost: number
  lowest: number
}

/** The cheapest split of the pictures into `rows` rows, in order (a linear partition). */
function bestSplit(ratios: readonly number[], rows: number): Split {
  const count = ratios.length
  // best[r][j]: the cheapest split of the first j pictures into r rows; from[r][j]: where its last
  // row starts. On a tie the later start wins: a shorter last row reads as the end of a set.
  const best = Array.from({ length: rows + 1 }, () => new Array<number>(count + 1).fill(Infinity))
  const from = Array.from({ length: rows + 1 }, () => new Array<number>(count + 1).fill(0))
  best[0][0] = 0
  for (let r = 1; r <= rows; r += 1) {
    for (let j = r; j <= count; j += 1) {
      for (let i = r - 1; i < j; i += 1) {
        const cost = best[r - 1][i] + rowCost(rowHeight(ratios, i, j))
        if (cost <= best[r][j]) {
          best[r][j] = cost
          from[r][j] = i
        }
      }
    }
  }
  const starts: number[] = []
  for (let r = rows, j = count; r > 0; r -= 1) {
    starts.unshift(from[r][j])
    j = from[r][j]
  }
  const ends = [...starts.slice(1), count]
  const lowest = Math.min(...starts.map((start, n) => rowHeight(ratios, start, ends[n])))
  return { starts, cost: best[rows][count], lowest }
}

/**
 * The rows of a gallery at full width, broken — in order — where they come out the most even
 * around the target height. As many rows as the count gives (`galleryRowCount`); more only while
 * a row would still be a strip and another row makes the whole cheaper (a panorama and a phone
 * shot that the count put together). A lone picture in the last row would be blown up, and costs
 * too much to be chosen unless it fills a row by itself. Exact up to `EXACT_UP_TO` pictures, a
 * greedy fill to the target past it.
 */
export function wideRows(ratios: readonly number[]): number[][] {
  const count = ratios.length
  if (count > EXACT_UP_TO) {
    const starts = [0]
    for (let end = 1; end < count; end += 1) {
      if (rowHeight(ratios, starts[starts.length - 1], end) <= TARGET_ROW) starts.push(end)
    }
    return rowsFromStarts(starts, count)
  }
  let split = bestSplit(ratios, Math.min(galleryRowCount(count), count))
  while (split.lowest < STRIP_ROW && split.starts.length < count) {
    const more = bestSplit(ratios, split.starts.length + 1)
    if (more.cost >= split.cost) break
    split = more
  }
  return rowsFromStarts(split.starts, count)
}

/**
 * The widths a gallery is laid out for, by the width of its container (`document.css` picks one
 * with a container query): balanced rows at full width, two in a row on a narrow body, one on a
 * very narrow one.
 */
export const GALLERY_MODES = ['wide', 'mid', 'narrow'] as const
export type GalleryMode = (typeof GALLERY_MODES)[number]

/** The rows of a gallery in a mode, as lists of picture indexes, from the pictures' proportions. */
export function galleryRows(ratios: readonly number[], mode: GalleryMode): number[][] {
  if (mode === 'wide') return wideRows(ratios)
  const columns = mode === 'mid' ? 2 : 1
  return rowsFromStarts(
    Array.from({ length: Math.ceil(ratios.length / columns) }, (_, n) => n * columns),
    ratios.length,
  )
}

/** The pictures (by index) a row starts with in a mode, the first one aside: where a row breaks. */
export function rowStarts(ratios: readonly number[]): { index: number; modes: GalleryMode[] }[] {
  const starts = new Map<number, GalleryMode[]>()
  for (const mode of GALLERY_MODES) {
    for (const row of galleryRows(ratios, mode).slice(1)) starts.set(row[0], [...(starts.get(row[0]) ?? []), mode])
  }
  return [...starts.entries()].sort(([a], [b]) => a - b).map(([index, modes]) => ({ index, modes }))
}

/**
 * The layout of each picture of a gallery from the proportions of all of them: its own ratio, and
 * for every mode the sum of the ratios of its row and how many share the row. A picture's width is
 * then its share of the row less the gaps (`document.css`), and its height follows from its ratio —
 * the same for the whole row. On a narrow body a short last row is divided as the row above it, so
 * it keeps that row's height rather than being blown up.
 */
export function galleryLayout(pictureRatios: readonly number[]): Record<string, string>[] {
  const vars: Record<string, string>[] = pictureRatios.map((ratio) => ({ '--r': ratio.toFixed(4) }))
  for (const mode of GALLERY_MODES) {
    const rows = galleryRows(pictureRatios, mode)
    rows.forEach((row, n) => {
      const short = mode !== 'wide' && n > 0 && n === rows.length - 1 && row.length < rows[0].length
      const measure = short ? rows[n - 1] : row
      const sum = measure.reduce((total, index) => total + pictureRatios[index], 0)
      for (const index of row) {
        vars[index][`--k-${mode}`] = String(measure.length)
        vars[index][`--s-${mode}`] = sum.toFixed(4)
      }
    })
  }
  return vars
}

/** The code a picture's markup carries — its pill's label, in both zones. */
export function pictureCode(tile: HTMLElement): string {
  return tile.querySelector('.md-ref-label')?.textContent?.trim() ?? ''
}

/**
 * Lay out the pictures of one gallery, given in order: their proportions (the neutral slot for
 * those not loaded as pictures) written as the custom properties the stylesheet sizes them by.
 */
export function layOutGallery(tiles: readonly HTMLElement[]): void {
  if (tiles.length < 2) return
  const layout = galleryLayout(tiles.map((tile) => ratioOf(pictureCode(tile))))
  tiles.forEach((tile, index) => {
    for (const [name, value] of Object.entries(layout[index])) {
      if (tile.style.getPropertyValue(name) !== value) tile.style.setProperty(name, value)
    }
  })
}

/**
 * The viewer's row breaks for one gallery: a break ahead of each picture that starts a row in some
 * width, put where the proportions now say. The editor draws the same breaks as decorations.
 */
export function placeRowBreaks(gallery: HTMLElement, tiles: readonly HTMLElement[]): void {
  const wanted = new Map(rowStarts(tiles.map((tile) => ratioOf(pictureCode(tile))))
    .map(({ index, modes }) => [tiles[index], rowBreakClasses(modes)]))
  for (const spot of [...gallery.querySelectorAll<HTMLElement>(':scope > .md-row-break')]) {
    const next = spot.nextElementSibling as HTMLElement | null
    if (next && wanted.get(next) === spot.className) wanted.delete(next)
    else spot.remove()
  }
  for (const [tile, classes] of wanted) {
    const spot = document.createElement('span')
    spot.className = classes
    gallery.insertBefore(spot, tile)
  }
}

/** The classes each picture of a gallery of `count` carries: its column count, and alone or not. */
export function pictureClasses(count: number): string[] {
  const classes = [`md-image--cols-${Math.min(4, galleryColumns(count))}`]
  if (count === 1) classes.push('md-image--single')
  return classes
}

/** The classes of the line break ahead of a picture that starts a row in these modes. */
export function rowBreakClasses(modes: readonly GalleryMode[]): string {
  return ['md-row-break', ...modes.map((mode) => `md-row-break--${mode}`)].join(' ')
}
