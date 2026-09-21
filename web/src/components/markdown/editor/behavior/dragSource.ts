// Пометка блоков-исходников на время переноса.
//
// Канон: исходный элемент ОСТАЁТСЯ на месте приглушённым — так видно, откуда вещь взяли и куда
// она вернётся, если место дропа не выбрано. Удалять блок из потока на время переноса нельзя:
// список схлопнется, соседи прыгнут, и точка отсчёта потеряется.
//
// Почему расширение, а не `classList.add` на элементе: ProseMirror держит своё представление
// документа и сбрасывает атрибуты, выставленные мимо него, — класс снимался сразу же. Всё, что
// видно в документе, но не является его содержимым, обязано быть декорацией.
import { Extension } from '@tiptap/core'
import { Plugin, PluginKey } from '@tiptap/pm/state'
import { Decoration, DecorationSet } from '@tiptap/pm/view'

const DRAG_SOURCE = new PluginKey<number[]>('dragSource')

declare module '@tiptap/core' {
  interface Commands<ReturnType> {
    dragSource: {
      /** Пометить блоки по позициям их начала. Пустой список снимает пометку. */
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
            // Позиции переезжают вместе с документом: дроп сдвигает всё, что было ниже.
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
