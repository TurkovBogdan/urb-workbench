// The card that follows the cursor while a block is being dragged.
//
// The browser draws the native preview from the element itself and makes it translucent — neither
// the opacity nor the shadow of the native snapshot can be controlled, it is a platform limit. The
// only way to get an opaque card is to drop the native preview entirely (with a transparent pixel)
// and drive our own by hand.
//
// The preview must match the original exactly: same width, same line breaks, same height.
// Otherwise the text reflows the moment it is grabbed, and that reads as "the font slipped".
import { ref } from 'vue'
import type { Ref } from 'vue'
import type { Editor } from '@tiptap/core'
import type { EditorView } from '@tiptap/pm/view'

// Created up front: the browser ignores an image that has not loaded and falls back to the
// default snapshot.
const EMPTY_DRAG_IMAGE = new Image()
EMPTY_DRAG_IMAGE.src = 'data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7'

interface DraggedBlock { pos: number; dom: HTMLElement }

export interface DragPreview {
  /** Whether a drag is in progress — the zone outlines itself while it is. */
  dragging: Ref<boolean>
  start: (event: DragEvent) => void
  end: () => void
  /** Remove the global listener and the card if unmounted mid-drag. */
  dispose: () => void
}

/**
 * @param editor  the editor; `undefined` until mounted
 * @param handlePos position of the block under the drag handle
 */
export function useDragPreview(
  editor: Ref<Editor | undefined>,
  handlePos: Ref<number | null>,
): DragPreview {
  const dragging = ref(false)
  let ghost: HTMLElement | null = null

  // The blocks that will move. A drag takes the whole selection, so the preview must show all of
  // it: a card with one paragraph when five are moving is a flat lie about what happens on
  // release.
  function draggedBlocks(view: EditorView): DraggedBlock[] {
    const { from, to } = view.state.selection
    const selected: DraggedBlock[] = []
    let handleInSelection = false

    view.state.doc.forEach((node, offset) => {
      if (offset >= to || offset + node.nodeSize <= from) return
      const dom = view.nodeDOM(offset)
      if (dom instanceof HTMLElement) selected.push({ pos: offset, dom })
      if (offset === handlePos.value) handleInSelection = true
    })

    // The selection is used only if it spans several blocks AND includes the one being dragged.
    // Otherwise the block under the handle moves while the caret may sit somewhere else entirely —
    // and the preview would show something other than what is moving.
    if (selected.length > 1 && handleInSelection) return selected

    const pos = handlePos.value
    const handled = pos === null ? null : view.nodeDOM(pos)
    if (pos !== null && handled instanceof HTMLElement) return [{ pos, dom: handled }]
    return selected
  }

  function buildPreview(sources: DraggedBlock[]): HTMLElement {
    // The host lives INSIDE the editing zone: outside it the clone would lose the component's
    // styles and arrive as bare text.
    const host = document.createElement('div')
    host.className = 'editor__preview'
    host.setAttribute('aria-hidden', 'true')

    const card = document.createElement('div')
    card.className = 'editor__preview-card'

    // A separate document layer: it carries the same typography as the document itself (the
    // `md-body` class from the shared file) and gets the EXACT width of the original. The width is
    // not styling here but the condition for a match: it decides where lines break, and so the
    // height.
    const body = document.createElement('div')
    body.className = 'md-body editor__preview-doc'
    body.style.width = `${sources[0].dom.offsetWidth}px`
    for (const source of sources) body.appendChild(source.dom.cloneNode(true))

    card.appendChild(body)
    host.appendChild(card)
    return host
  }

  // The card moves by transform only: shifting it via `left`/`top` would recompute layout on
  // every frame.
  function moveGhost(x: number, y: number): void {
    if (ghost) ghost.style.transform = `translate3d(${x - 24}px, ${y - 24}px, 0)`
  }

  function trackGhost(event: DragEvent): void {
    moveGhost(event.clientX, event.clientY)
  }

  function start(event: DragEvent): void {
    dragging.value = true

    const view = editor.value?.view
    if (!view || !event.dataTransfer) return
    const sources = draggedBlocks(view)
    if (!sources.length) return

    ghost = buildPreview(sources)
    view.dom.parentElement?.appendChild(ghost)
    moveGhost(event.clientX, event.clientY)

    event.dataTransfer.setDragImage(EMPTY_DRAG_IMAGE, 0, 0)
    // Coordinates come from `dragover`: on the `drag` event some browsers report zeros.
    document.addEventListener('dragover', trackGhost)

    editor.value?.commands.markDragSource(sources.map((source) => source.pos))
  }

  // Any end of a drag: a drop, a cancel with Esc, a release off target.
  //
  // prosemirror-dropcursor attaches its handlers to `editorView.dom` itself, while our drag source
  // is the handle, which sits next to it rather than inside. So `dragend` never reaches the plugin,
  // and after a cancel the insertion line is left hanging on screen. We forward the event inside:
  // debris after a cancel is an anti-pattern of its own, and the indicator must be cleared by the
  // event that also arrives on failure.
  function end(): void {
    // A drag this preview never started (text pulled inside the document) ends on its own.
    if (!dragging.value) return
    dragging.value = false

    document.removeEventListener('dragover', trackGhost)
    ghost?.remove()
    ghost = null

    editor.value?.commands.markDragSource([])
    editor.value?.view.dom.dispatchEvent(new DragEvent('dragend', { bubbles: false }))
  }

  function dispose(): void {
    document.removeEventListener('dragover', trackGhost)
    ghost?.remove()
    ghost = null
  }

  return { dragging, start, end, dispose }
}
