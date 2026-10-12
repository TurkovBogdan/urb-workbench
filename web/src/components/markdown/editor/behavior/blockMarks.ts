// Where a block's handle stands, and a resting handle mark beside every block.
//
// The live handle is the drag-handle extension's one floating element: it follows the block under
// the pointer and is what a drag actually starts from. The marks are its resting image — one per
// top-level block, drawn where the live handle would land on that block, inert to the pointer. Under
// the pointer the live handle covers its block's mark exactly, so every block reads as having a
// handle while the extension still runs the gesture.
//
// Both sit at the same point because both are placed by `handleTop`: a block with text puts the
// handle's centre on its first line, not on the block's top edge — a heading's line is taller than
// the handle, a code block opens with a header; a picture (a diagram) puts the handle level with
// the picture's top.
import { onBeforeUnmount, onMounted, ref, watch, type Ref } from 'vue'
import type { Editor } from '@tiptap/core'

/** A block with no text, at most this tall, is centred on; a taller one keeps the handle at its top. */
const TEXTLESS_CENTRED_MAX = 40

/** Smaller than this, an <svg> or <img> is an icon beside the content, not the content itself. */
const PICTURE_MIN_HEIGHT = 24

// The letter whose height stands for the line's capitals: Cyrillic Н and Latin H share it.
const CAP_PROBE = 'Н'

let measuring: CanvasRenderingContext2D | null = null

/**
 * The middle of the capitals, as a distance below the top of the text's box. The box a text range
 * reports is the font's whole ascent-to-descent area, and in Onest that area is not symmetric
 * about the letters: its centre sat 1.8px below the capitals of an h1, 0.9px below a paragraph's
 * — visibly low next to a large heading. The eye reads a line by its capitals, so that is the
 * middle the handle meets. `null` — the browser gives no font metrics; the box centre stands in.
 */
function capitalsMiddle(element: Element): number | null {
  measuring ??= document.createElement('canvas').getContext('2d')
  if (!measuring) return null
  const style = getComputedStyle(element)
  measuring.font = `${style.fontStyle} ${style.fontWeight} ${style.fontSize} ${style.fontFamily}`
  const metrics = measuring.measureText(CAP_PROBE)
  if (!metrics.fontBoundingBoxAscent) return null
  return metrics.fontBoundingBoxAscent - metrics.actualBoundingBoxAscent / 2
}

/**
 * The middle of the block's first line, as a distance from its top edge. The line is the block's
 * first visible text: a heading's larger type, a paragraph's line, a code block's header (its
 * language name is the first text in it), a table's first cell. `null` — the block has no line.
 */
function firstLineMiddle(block: HTMLElement, top: number): number | null {
  const walker = document.createTreeWalker(block, NodeFilter.SHOW_TEXT)
  for (let text = walker.nextNode(); text; text = walker.nextNode()) {
    if (!text.textContent?.trim()) continue
    // A diagram's text is not a line of the block: its labels are drawn inside the picture, its
    // "Edit" is a button, and its caption ("double click — fullscreen") sits UNDER the picture — a
    // handle on that line stood at the diagram's foot, reading as the next section's.
    if (!text.parentElement || text.parentElement.closest('svg, button, figcaption')) continue
    const range = document.createRange()
    range.selectNodeContents(text)
    const line = range.getClientRects()[0]
    if (!line || line.height <= 0) continue
    const middle = capitalsMiddle(text.parentElement) ?? line.height / 2
    return line.top + middle - top
  }
  return null
}

/** The top of the block's picture — a rendered diagram — as a distance from the block's top. */
function pictureTop(block: HTMLElement, top: number): number | null {
  for (const picture of block.querySelectorAll('svg, img')) {
    const box = picture.getBoundingClientRect()
    if (box.height >= PICTURE_MIN_HEIGHT && !picture.closest('button')) return box.top - top
  }
  return null
}

/**
 * Where a handle `height` tall stands beside the block, as a distance from the block's top edge:
 * centred on the first line; level with the top of the picture for a block that is a picture; for
 * a block with neither, centred on a short block and at the top of a tall one.
 */
export function handleTop(block: HTMLElement, height: number): number {
  const box = block.getBoundingClientRect()
  const line = firstLineMiddle(block, box.top)
  if (line !== null) return line - height / 2
  const picture = pictureTop(block, box.top)
  if (picture !== null) return picture
  return box.height <= TEXTLESS_CENTRED_MAX ? (box.height - height) / 2 : 0
}

export interface BlockMark {
  /** The block's position — a stable key while the document does not change around it. */
  pos: number
  top: number
  left: number
}

/**
 * Resting marks for every top-level block, in the coordinates of `frame` — the element the live
 * handle is positioned against, so a mark and the handle meet. Recomputed after every transaction
 * and whenever the document's box changes size (a wrap, a font arriving, the window resizing).
 *
 * @param size the handle's box; the mark is laid out like the handle (`left-start`).
 */
export function useBlockMarks(
  editor: Ref<Editor | undefined>,
  frame: Ref<HTMLElement | null>,
  enabled: Ref<boolean>,
  tick: Ref<number>,
  size: { width: number; height: number },
): Ref<BlockMark[]> {
  const marks = ref<BlockMark[]>([])
  let frameRequest = 0

  function measure(): void {
    frameRequest = 0
    const view = editor.value?.view
    const root = frame.value
    // An empty field is one empty line: there is nothing to move, and a handle beside its
    // placeholder would offer to.
    const doc = view?.state.doc
    const empty = !!doc && doc.childCount === 1 && doc.firstChild!.isTextblock && doc.firstChild!.content.size === 0
    if (!enabled.value || !view || !root || !editor.value?.isEditable || empty) {
      marks.value = []
      return
    }
    // Absolute positions count from inside the frame's border, the box from outside it: an
    // outlined zone's 1px border put every mark a pixel off the live handle. The width is read from
    // the style, not `clientTop`: that rounds, and a scaled page draws the border at 0.9px.
    const frameBox = root.getBoundingClientRect()
    const frameStyle = getComputedStyle(root)
    const origin = {
      top: frameBox.top + parseFloat(frameStyle.borderTopWidth),
      left: frameBox.left + parseFloat(frameStyle.borderLeftWidth),
    }
    const next: BlockMark[] = []
    view.state.doc.forEach((_node, offset) => {
      const dom = view.nodeDOM(offset)
      if (!(dom instanceof HTMLElement)) return
      const box = dom.getBoundingClientRect()
      next.push({
        pos: offset,
        top: box.top - origin.top + handleTop(dom, size.height),
        left: box.left - origin.left - size.width,
      })
    })
    marks.value = next
  }

  function schedule(): void {
    if (!frameRequest) frameRequest = requestAnimationFrame(measure)
  }

  watch([tick, enabled], schedule)

  let resize: ResizeObserver | null = null
  onMounted(() => {
    resize = new ResizeObserver(schedule)
    watch(
      () => editor.value?.view.dom,
      (dom, previous) => {
        if (previous) resize?.unobserve(previous)
        if (dom) resize?.observe(dom)
        schedule()
      },
      { immediate: true },
    )
    void document.fonts?.ready.then(schedule)
  })

  onBeforeUnmount(() => {
    resize?.disconnect()
    if (frameRequest) cancelAnimationFrame(frameRequest)
  })

  return marks
}
