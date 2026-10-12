// Where a dragged block will land, shown the way the task list shows it: as the room the block
// will take. A slot as tall as the dragged blocks opens between two blocks and the blocks below
// make way; the source stays where it was, faded (`dragSource.ts`), until the drop.
//
// It replaces prosemirror-dropcursor's line for block drags only — a drag that did not start on
// the handle (a file or text from outside) has no source and still gets the line.
//
// The drop is done here too. ProseMirror would place the block by the drop's coordinates, and
// those now fall on the slot, which is not part of the document; the slot already knows the
// boundary it stands for, so the move goes exactly where it was shown.
import { Extension } from '@tiptap/core'
import { Plugin, PluginKey, TextSelection } from '@tiptap/pm/state'
import { Decoration, DecorationSet, type EditorView } from '@tiptap/pm/view'
import { DRAG_SOURCE } from './dragSource'
import { FLASH } from './blockMoves'

interface SlotState {
  /** The boundary between top-level blocks the slot stands at; `null` — no slot. */
  target: number | null
  height: number
}

const DROP_SLOT = new PluginKey<SlotState>('dropSlot')
const NO_SLOT: SlotState = { target: null, height: 0 }
const SLOT_CLASS = 'editor__drop-slot'

interface Source {
  from: number
  to: number
  height: number
}

/** The dragged range — first source block to the end of the last — and its height on screen. */
function sourceOf(view: EditorView): Source | null {
  const positions = DRAG_SOURCE.getState(view.state)
  if (!positions?.length) return null
  const sorted = [...positions].sort((a, b) => a - b)
  const first = sorted[0]
  const last = sorted[sorted.length - 1]
  const lastNode = view.state.doc.nodeAt(last)
  const firstDom = view.nodeDOM(first)
  const lastDom = view.nodeDOM(last)
  if (!lastNode || !(firstDom instanceof HTMLElement) || !(lastDom instanceof HTMLElement)) return null
  const height = lastDom.getBoundingClientRect().bottom - firstDom.getBoundingClientRect().top
  return { from: first, to: last + lastNode.nodeSize, height }
}

/**
 * The boundary the pointer points at: before the first block whose middle is below it, or the
 * document's end. While the pointer is over the slot itself the slot stays — it pushed the blocks
 * below it down, and measured against them the pointer would jump the slot back and forth.
 */
function boundaryAt(view: EditorView, y: number, current: number | null): number | null {
  const slot = view.dom.querySelector(`.${SLOT_CLASS}`)
  if (slot) {
    const box = slot.getBoundingClientRect()
    if (y >= box.top && y <= box.bottom) return current
  }
  let boundary: number | null = null
  view.state.doc.forEach((_node, offset) => {
    if (boundary !== null) return
    const dom = view.nodeDOM(offset)
    if (!(dom instanceof HTMLElement)) return
    const box = dom.getBoundingClientRect()
    if (y < box.top + box.height / 2) boundary = offset
  })
  return boundary ?? view.state.doc.content.size
}

function show(view: EditorView, next: SlotState): void {
  const current = DROP_SLOT.getState(view.state)
  if (current?.target === next.target && current.height === next.height) return
  view.dispatch(view.state.tr.setMeta(DROP_SLOT, next))
}

export const DropSlot = Extension.create({
  name: 'dropSlot',

  addProseMirrorPlugins() {
    return [
      new Plugin<SlotState>({
        key: DROP_SLOT,

        state: {
          init: () => NO_SLOT,
          apply(tr, value) {
            const next = tr.getMeta(DROP_SLOT) as SlotState | undefined
            if (next) return next
            if (value.target === null || !tr.docChanged) return value
            return { ...value, target: tr.mapping.map(value.target) }
          },
        },

        props: {
          decorations(state) {
            const { target, height } = DROP_SLOT.getState(state) ?? NO_SLOT
            if (target === null) return null
            const slot = Decoration.widget(target, () => {
              const element = document.createElement('div')
              element.className = SLOT_CLASS
              element.style.height = `${height}px`
              element.contentEditable = 'false'
              element.setAttribute('aria-hidden', 'true')
              return element
            }, { side: -1, key: `${SLOT_CLASS}-${height}`, ignoreSelection: true })
            return DecorationSet.create(state.doc, [slot])
          },

          handleDOMEvents: {
            dragover(view, event) {
              const source = sourceOf(view)
              if (!source) return false
              const current = DROP_SLOT.getState(view.state)?.target ?? null
              const boundary = boundaryAt(view, event.clientY, current)
              // On the source itself or right next to it the block would not move: no slot, and
              // the faded source says "it stays here".
              const target = boundary === null || (boundary >= source.from && boundary <= source.to)
                ? null
                : boundary
              show(view, { target, height: target === null ? 0 : source.height })
              return false
            },
            dragleave(view, event) {
              const into = event.relatedTarget as Node | null
              if (into && view.dom.contains(into)) return false
              show(view, NO_SLOT)
              return false
            },
            dragend(view) {
              show(view, NO_SLOT)
              return false
            },

            // Taken as a DOM event, before ProseMirror's own drop handling: that one first looks
            // the drop's coordinates up in the document, and over the slot — which is not in the
            // document — the lookup can fail and end the drop before any `handleDrop` is asked.
            //
            // Every outcome leaves a caret, never a selection. The drag handle extension, on the
            // drop, remembers a non-empty selection and puts it back over the dropped blocks; a
            // block group moved by its handle stayed selected after the drop, and one let go over
            // itself kept the selection the drag had started with.
            drop(view, event) {
              const source = sourceOf(view)
              if (!source) return false
              event.preventDefault()
              view.dragging = null
              const { target } = DROP_SLOT.getState(view.state) ?? NO_SLOT
              const tr = view.state.tr.setMeta(DROP_SLOT, NO_SLOT)
              // Let go over the source, or with no slot open: nothing moves.
              if (target === null) {
                tr.setSelection(TextSelection.near(tr.doc.resolve(source.from + 1)))
                view.dispatch(tr)
                return true
              }
              const content = view.state.doc.slice(source.from, source.to).content
              tr.delete(source.from, source.to)
              const landed = tr.mapping.map(target)
              tr.insert(landed, content)
              tr.setSelection(TextSelection.near(tr.doc.resolve(landed + 1)))
              tr.setMeta(FLASH, landed)
              tr.scrollIntoView()
              view.dispatch(tr)
              return true
            },
          },
        },
      }),
    ]
  },
})
