// Marks the source blocks for the duration of a drag.
//
// The canon: the source element STAYS in place, dimmed — that shows where the thing was taken
// from and where it returns if no drop target is chosen. Removing the block from the flow during
// the drag is not allowed: the list would collapse, the neighbours would jump, and the point of
// reference would be lost.
//
// Why an extension rather than `classList.add` on the element: ProseMirror keeps its own view of
// the document and resets attributes set behind its back — the class was removed immediately.
// Anything visible in the document that is not its content has to be a decoration.
import { Extension } from '@tiptap/core'
import { Plugin, PluginKey } from '@tiptap/pm/state'
import { Decoration, DecorationSet } from '@tiptap/pm/view'

const DRAG_SOURCE = new PluginKey<number[]>('dragSource')

declare module '@tiptap/core' {
  interface Commands<ReturnType> {
    dragSource: {
      /** Mark blocks by their start positions. An empty list clears the mark. */
      markDragSource: (positions: number[]) => ReturnType
    }
  }
}

export const DragSource = Extension.create({
  name: 'dragSource',

  addCommands() {
    return {
      markDragSource: (positions) => ({ tr, dispatch }) => {
        if (dispatch) tr.setMeta(DRAG_SOURCE, positions)
        return true
      },
    }
  },

  addProseMirrorPlugins() {
    return [
      new Plugin<number[]>({
        key: DRAG_SOURCE,

        state: {
          init: () => [],
          apply(tr, value) {
            const next = tr.getMeta(DRAG_SOURCE)
            if (next !== undefined) return next as number[]
            // Positions move with the document: the drop shifts everything that was below.
            return value.length ? value.map((pos) => tr.mapping.map(pos)) : value
          },
        },

        props: {
          decorations(state) {
            const positions = DRAG_SOURCE.getState(state)
            if (!positions?.length) return null

            const decorations: Decoration[] = []
            for (const pos of positions) {
              const node = state.doc.nodeAt(pos)
              if (node) decorations.push(Decoration.node(pos, pos + node.nodeSize, { class: 'is-drag-source' }))
            }
            return DecorationSet.create(state.doc, decorations)
          },
        },
      }),
    ]
  },
})
