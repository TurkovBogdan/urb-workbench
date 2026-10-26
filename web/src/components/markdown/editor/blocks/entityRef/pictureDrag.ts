// Dragging a picture to another place in the text: within its gallery, into another one, or out of
// it into a line of text. The edit itself is `pictureMove.ts`; this is the gesture.
//
// POINTER EVENTS, NOT NATIVE DRAG — the research's rule for a move inside the page
// (RESEARCH@0b534e01e9): native drag sends nothing for a finger, gives the preview to the browser and
// freezes scrolling while it runs. The editor's blocks move natively only because the drag handle
// extension does; a picture has no handle — the picture itself is taken.
//
// THE GESTURE. A mouse takes the picture once the pointer has travelled 4 px with the button held —
// less stays a click, which selects the picture (ProseMirror), and a double click still opens it.
// ProseMirror's own press ends harmlessly: past 4 px it leaves the selection alone. A finger or a pen
// takes it after a 250 ms hold without moving; moving sooner is the page's scroll, and once the
// picture is taken the page stops scrolling under the finger.
//
// While it is held the picture stays where it was, faded — where it came from and where it goes back
// to; a card with it follows the pointer, and a line says where it lands: between two pictures — in
// the gap between them; between two blocks or along a block's edge — across the block, and the
// picture opens a line of its own there; in a line of text — at the seam, a caret tall. No line,
// nothing changes on release. Near the top or bottom of the scroller the page scrolls toward the pointer. Escape, or
// letting go off the field, puts the picture back.
import { Plugin, PluginKey, type EditorState } from '@tiptap/pm/state'
import { Decoration, DecorationSet, type EditorView } from '@tiptap/pm/view'
import { movePicture, nearestSeam } from './pictureMove'
import { isImageCode } from './imageRuns'

/** A short twitch with the button held is still a click. The app's lists use the same. */
const GRAB_TOLERANCE_PX = 4
/** The hold that takes a picture under a finger, as in the codex tree. */
const TOUCH_HOLD_MS = 250
/** A finger is never still; past this it is scrolling. */
const TOUCH_SLOP_PX = 8
/** The strip along a block's top and bottom edge that means "a line of its own", not "into this line". */
const LINE_EDGE_PX = 6
/** The card's longest side: big enough to recognise, small enough not to cover the target. */
const PREVIEW_MAX_PX = 160
/** Auto-scroll zone: a quarter of the scroller or 180 px, whichever is smaller (the research's numbers). */
const SCROLL_ZONE_SHARE = 0.25
const SCROLL_ZONE_MAX_PX = 180
const SCROLL_MAX_SPEED = 900
/** A picture taken at the very edge must not shoot the page away at once: the speed ramps up. */
const SCROLL_RAMP_MS = 400

export interface PictureDragOptions {
  /** A picture is being held — the editor quiets what would answer the pointer meanwhile. */
  onDragging?: (on: boolean) => void
}

/** Position of the picture being dragged — drawn faded; `null` — no drag. */
const PICTURE_DRAG = new PluginKey<number | null>('pictureDrag')

interface Line { left: number; top: number; width: number; height: number }
interface Target { pos: number; line: Line }

function isPictureAt(state: EditorState, pos: number): boolean {
  const node = state.doc.nodeAt(pos)
  return !!node && node.type.name === 'entityRef' && isImageCode(String(node.attrs.code ?? ''))
}

/** The position of the picture a node view draws. */
export function posOfTile(view: EditorView, tile: Element): number | null {
  let found: number | null = null
  view.state.doc.descendants((node, pos) => {
    if (found !== null) return false
    if (node.type.name === 'entityRef' && view.nodeDOM(pos) === tile) found = pos
    return found === null
  })
  return found
}

/** The element whose scrolling brings more of the field into view. */
function scrollerOf(element: Element): HTMLElement {
  for (let node = element.parentElement; node; node = node.parentElement) {
    const { overflowY } = getComputedStyle(node)
    if ((overflowY === 'auto' || overflowY === 'scroll') && node.scrollHeight > node.clientHeight) return node
  }
  return (document.scrollingElement as HTMLElement | null) ?? document.documentElement
}

export function pictureDrag(options: PictureDragOptions): Plugin<number | null> {
  return new Plugin<number | null>({
    key: PICTURE_DRAG,
    state: {
      init: () => null,
      apply(tr, value) {
        const next = tr.getMeta(PICTURE_DRAG) as number | null | undefined
        if (next !== undefined) return next
        return value === null ? null : tr.mapping.map(value)
      },
    },
    props: {
      decorations(state) {
        const pos = PICTURE_DRAG.getState(state)
        if (pos === null || pos === undefined || !isPictureAt(state, pos)) return null
        return DecorationSet.create(state.doc, [Decoration.node(pos, pos + 1, { class: 'md-image--drag-source' })])
      },
    },
    view(view) {
      const gesture = createGesture(view, options)
      view.dom.addEventListener('pointerdown', gesture.press)
      return {
        destroy() {
          view.dom.removeEventListener('pointerdown', gesture.press)
          gesture.dispose()
        },
      }
    },
  })
}

interface Press {
  pointerId: number
  touch: boolean
  x: number
  y: number
  pos: number
  tile: HTMLElement
  hold: ReturnType<typeof setTimeout> | null
}

interface Drag {
  pos: number
  tile: HTMLElement
  ghost: HTMLElement
  line: HTMLElement
  grabX: number
  grabY: number
  x: number
  y: number
  target: Target | null
  scroller: HTMLElement
  started: number
  frame: number
  lastFrame: number
}

function createGesture(view: EditorView, options: PictureDragOptions) {
  let press: Press | null = null
  let drag: Drag | null = null

  function down(event: PointerEvent): void {
    if (press || drag || !view.editable || !event.isPrimary) return
    if (event.pointerType === 'mouse' && event.button !== 0) return
    // Shift extends the selection, the others are the system's or the editor's.
    if (event.shiftKey || event.altKey || event.ctrlKey || event.metaKey) return
    const target = event.target as Element | null
    if (!target || target.closest('.md-image__copy')) return
    const tile = target.closest<HTMLElement>('.md-image--shown')
    if (!tile || !view.dom.contains(tile)) return
    const pos = posOfTile(view, tile)
    if (pos === null) return

    press = {
      pointerId: event.pointerId,
      touch: event.pointerType === 'touch',
      x: event.clientX,
      y: event.clientY,
      pos,
      tile,
      hold: null,
    }
    if (press.touch) press.hold = setTimeout(() => begin(), TOUCH_HOLD_MS)
    window.addEventListener('pointermove', move, true)
    window.addEventListener('pointerup', release, true)
    window.addEventListener('pointercancel', abandon, true)
    window.addEventListener('keydown', key, true)
    window.addEventListener('blur', abandon)
    // A held finger brings up the system menu of a picture; a held picture must not.
    window.addEventListener('contextmenu', quiet, true)
    // A picture selected already is made draggable by ProseMirror itself on the press, and the
    // browser's own drag that follows cancels this gesture's pointer: the picture just sat still.
    window.addEventListener('dragstart', quiet, true)
    // Cancelling a touch move is the one way to keep the page still under a finger once the picture
    // is taken: the browser decided on its own scrolling when the touch began.
    window.addEventListener('touchmove', still, { capture: true, passive: false })
  }

  function quiet(event: Event): void {
    event.preventDefault()
  }

  function still(event: TouchEvent): void {
    if (drag) event.preventDefault()
  }

  function move(event: PointerEvent): void {
    if (!press || event.pointerId !== press.pointerId) return
    if (drag) {
      drag.x = event.clientX
      drag.y = event.clientY
      follow()
      return
    }
    const distance = Math.hypot(event.clientX - press.x, event.clientY - press.y)
    if (press.touch) {
      if (distance > TOUCH_SLOP_PX) stop()
      return
    }
    if (distance >= GRAB_TOLERANCE_PX) begin(event.clientX, event.clientY)
  }

  function begin(x = press?.x ?? 0, y = press?.y ?? 0): void {
    if (!press || drag) return
    const { pos, tile } = press
    if (press.hold) clearTimeout(press.hold)
    press.hold = null
    // The document may have changed under a held finger.
    if (!isPictureAt(view.state, pos) || view.nodeDOM(pos) !== tile) {
      stop()
      return
    }

    const box = tile.getBoundingClientRect()
    const scale = Math.min(1, PREVIEW_MAX_PX / Math.max(box.width, box.height, 1))
    const host = view.dom.parentElement ?? document.body
    const ghost = document.createElement('div')
    ghost.className = 'md-image-drag-preview'
    ghost.setAttribute('aria-hidden', 'true')
    ghost.style.width = `${box.width * scale}px`
    ghost.style.height = `${box.height * scale}px`
    const picture = tile.querySelector('img')
    if (picture) {
      const copy = document.createElement('img')
      copy.src = picture.currentSrc || picture.src
      copy.alt = ''
      ghost.appendChild(copy)
    }
    const line = document.createElement('div')
    line.className = 'md-image-drop-line'
    line.setAttribute('aria-hidden', 'true')
    host.append(ghost, line)

    drag = {
      pos,
      tile,
      ghost,
      line,
      // The card is held by the point it was taken at, scaled with it.
      grabX: (x - box.left) * scale,
      grabY: (y - box.top) * scale,
      x,
      y,
      target: null,
      scroller: scrollerOf(view.dom),
      started: performance.now(),
      frame: 0,
      lastFrame: performance.now(),
    }
    document.body.classList.add('md-picture-dragging')
    options.onDragging?.(true)
    view.dispatch(view.state.tr.setMeta(PICTURE_DRAG, pos).setMeta('addToHistory', false))
    follow()
    drag.frame = requestAnimationFrame(scroll)
  }

  function follow(): void {
    if (!drag) return
    drag.ghost.style.transform = `translate3d(${drag.x - drag.grabX}px, ${drag.y - drag.grabY}px, 0)`
    drag.target = targetAt(drag.x, drag.y)
    const { line } = drag
    if (!drag.target) {
      line.style.visibility = 'hidden'
      return
    }
    const { left, top, width, height } = drag.target.line
    // The line glides from place to place, but a line just shown starts where it stands: from its
    // last place, or from the corner of the screen at first, the glide would draw it flying in. So
    // does a line that turns from upright to lying across a block.
    const across = width > height
    const appearing = line.style.visibility !== 'visible' || line.dataset.across !== String(across)
    if (appearing) line.style.transition = 'none'
    line.dataset.across = String(across)
    line.style.visibility = 'visible'
    line.style.width = `${width}px`
    line.style.height = `${height}px`
    line.style.transform = `translate3d(${left}px, ${top}px, 0)`
    if (appearing) {
      void line.offsetWidth
      line.style.transition = ''
    }
  }

  /**
   * Where the picture lands if let go at the point — only where the text would change. In order:
   * beside another picture; between two blocks, on a line of its own; inside a line of text.
   */
  function targetAt(x: number, y: number): Target | null {
    if (!drag) return null
    const element = document.elementFromPoint(x, y)
    // The field's own frame counts too: below its last block lies the place for a line at the end.
    const field = view.dom.parentElement ?? view.dom
    if (!element || !field.contains(element) || drag.tile.contains(element)) return null
    const target = besidePicture(element, x) ?? betweenBlocks(y) ?? inLine(x, y)
    if (!target || !movePicture(view.state, drag.pos, target.pos)) return null
    return target
  }

  // Pictures stand in rows: the half under the pointer says on which side the picture goes, and the
  // line stands in the gap on that side.
  function besidePicture(element: Element, x: number): Target | null {
    const tile = element.closest<HTMLElement>('.md-image')
    if (!tile || !view.dom.contains(tile)) return null
    const at = posOfTile(view, tile)
    if (at === null) return null
    const box = tile.getBoundingClientRect()
    const ahead = x < box.left + box.width / 2
    const gap = parseFloat(getComputedStyle(tile).getPropertyValue('--md-gallery-gap')) || 8
    const left = ahead ? box.left - gap / 2 : box.right + gap / 2
    return { pos: ahead ? at : at + 1, line: { left: left - 1, top: box.top, width: 2, height: box.height } }
  }

  // The gap between two blocks, and a strip along a block's top and bottom edge, mean "a line of its
  // own here": the line lies across the block, as the block drag's does.
  function betweenBlocks(y: number): Target | null {
    const blocks: { pos: number; box: DOMRect }[] = []
    view.state.doc.forEach((_node, offset) => {
      const dom = view.nodeDOM(offset)
      if (dom instanceof HTMLElement) blocks.push({ pos: offset, box: dom.getBoundingClientRect() })
    })
    for (let index = 0; index <= blocks.length; index += 1) {
      const above = blocks[index - 1]
      const below = blocks[index]
      if (above && y < above.box.bottom - LINE_EDGE_PX) continue
      if (below && y > below.box.top + LINE_EDGE_PX) continue
      const span = (above ?? below)?.box
      if (!span) return null
      const middle = above && below ? (above.box.bottom + below.box.top) / 2 : above ? above.box.bottom + 4 : span.top - 4
      return {
        pos: below ? below.pos : view.state.doc.content.size,
        line: { left: span.left, top: middle - 1, width: span.width, height: 2 },
      }
    }
    return null
  }

  // Inside a line of text: at the seam nearest the pointer, a caret tall.
  function inLine(x: number, y: number): Target | null {
    const found = view.posAtCoords({ left: x, top: y })
    if (!found) return null
    const pos = nearestSeam(view.state.doc, found.pos)
    const caret = view.coordsAtPos(pos)
    return { pos, line: { left: caret.left - 1, top: caret.top, width: 2, height: caret.bottom - caret.top } }
  }

  // The research's auto-scroll: within the zone the outer half runs at full speed and the inner
  // half ramps up to it linearly; px per second, measured by the frame's own time.
  function scroll(now: number): void {
    if (!drag) return
    const elapsed = Math.min(now - drag.lastFrame, 50)
    drag.lastFrame = now
    const { scroller } = drag
    const page = scroller === document.scrollingElement || scroller === document.documentElement
    const box = page ? { top: 0, bottom: window.innerHeight } : scroller.getBoundingClientRect()
    const zone = Math.min((box.bottom - box.top) * SCROLL_ZONE_SHARE, SCROLL_ZONE_MAX_PX)
    const share = (depth: number): number => (depth >= zone ? 0 : depth <= zone / 2 ? 1 : (zone - depth) / (zone / 2))
    const up = share(Math.max(0, drag.y - box.top))
    const down = share(Math.max(0, box.bottom - drag.y))
    const ramp = Math.min(1, (now - drag.started) / SCROLL_RAMP_MS)
    const speed = (down - up) * SCROLL_MAX_SPEED * ramp
    if (speed) {
      const before = scroller.scrollTop
      scroller.scrollTop += (speed * elapsed) / 1000
      if (scroller.scrollTop !== before) follow()
    }
    drag.frame = requestAnimationFrame(scroll)
  }

  function release(event: PointerEvent): void {
    if (!press || event.pointerId !== press.pointerId) return
    const landing = drag?.target ?? null
    const from = drag?.pos ?? null
    stop()
    if (landing === null || from === null) return
    const tr = movePicture(view.state, from, landing.pos)
    if (!tr) return
    view.dispatch(tr.scrollIntoView())
    view.focus()
  }

  function key(event: KeyboardEvent): void {
    if (event.key !== 'Escape' || !drag) return
    // The field and the dialog around it must not take this Escape too.
    event.preventDefault()
    event.stopPropagation()
    stop()
  }

  function abandon(): void {
    stop()
  }

  /**
   * The gesture ends with nothing moved: listeners off, the card and the line gone, the source back.
   * `restore: false` — the editor is being destroyed: its view takes no more transactions, and the
   * faded source goes with it.
   */
  function stop(restore = true): void {
    if (press?.hold) clearTimeout(press.hold)
    press = null
    window.removeEventListener('pointermove', move, true)
    window.removeEventListener('pointerup', release, true)
    window.removeEventListener('pointercancel', abandon, true)
    window.removeEventListener('keydown', key, true)
    window.removeEventListener('blur', abandon)
    window.removeEventListener('contextmenu', quiet, true)
    window.removeEventListener('dragstart', quiet, true)
    window.removeEventListener('touchmove', still, true)
    if (!drag) return
    cancelAnimationFrame(drag.frame)
    drag.ghost.remove()
    drag.line.remove()
    drag = null
    document.body.classList.remove('md-picture-dragging')
    options.onDragging?.(false)
    if (restore) view.dispatch(view.state.tr.setMeta(PICTURE_DRAG, null).setMeta('addToHistory', false))
  }

  return { press: down, dispose: () => stop(false) }
}
