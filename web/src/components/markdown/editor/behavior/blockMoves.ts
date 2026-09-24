// Перемещение блока без перетаскивания — и подтверждение того, что перемещение случилось.
//
// Порядок внедрения взят из исследования RESEARCH@0b534e01e9: сначала альтернативный путь,
// потом драг. Причины три, и все три практические.
//
// 1. Норма. WCAG 2.2 SC 2.5.7 (AA) требует, чтобы у каждого исхода перетаскивания был путь
//    одним нажатием указателя, без самого перетаскивания. Клавиатурная эмуляция драга этот
//    критерий НЕ закрывает — там нужен именно указатель. Отдельно SC 2.1.1 (A) требует, чтобы
//    то же действие выполнялось с клавиатуры. Это два разных требования, и одно не заменяет
//    другое: меню закрывает первое, сочетания клавиш — второе.
// 2. Страховка. Пока драг не доведён, переместить блок всё равно можно.
// 3. Экономия. Клавиатурная часть опирается на те же команды, что и меню; построй мы её после
//    драга — переписывать обработчики пришлось бы дважды.
//
// Раскладка `Alt+↑/↓` и `Alt+Shift+↑/↓` взята у Linear как разобранный в исследовании эталон.
// Удержание клавиш не требуется нигде: тайминги на нажатии запрещены SC 2.1.1.
import { Extension } from '@tiptap/core'
import type { EditorState, Transaction } from '@tiptap/pm/state'
import { Plugin, PluginKey, TextSelection } from '@tiptap/pm/state'
import { Decoration, DecorationSet } from '@tiptap/pm/view'

/** Куда двигать блок. `start` / `end` — в начало и конец документа. */
export type MoveTarget = 'up' | 'down' | 'start' | 'end'

export interface BlockMovesOptions {
  /**
   * Where the block landed, for the live region — as positions, not indexes. The words belong to
   * the editor, which knows the interface language; the extension only reports the numbers.
   */
  onAnnounce: ((position: number, total: number) => void) | null
}

declare module '@tiptap/core' {
  interface Commands<ReturnType> {
    blockMoves: {
      moveBlock: (target: MoveTarget) => ReturnType
    }
  }
}

// Вспышка на перемещённом блоке: 700 мс — величина из дизайн-фреймворка Atlassian. Нужна
// потому, что после перемещения взгляд теряет объект среди соседей: блок встал на место, но
// пользователь не уверен, встал ли он туда.
const FLASH_MS = 700
const FLASH = new PluginKey<number | null>('blockMoveFlash')

// ── Команда ───────────────────────────────────────────────────────────────────

interface TopBlock { pos: number; index: number; size: number }

function topBlock(state: EditorState): TopBlock | null {
  const { $from } = state.selection
  // Каретка внутри блока — обычный случай. Глубина 0 — это выделение блока целиком: так его
  // выделяет ручка перед открытием меню, и команда обязана понимать оба вида.
  const pos = $from.depth >= 1 ? $from.before(1) : $from.pos
  const node = state.doc.nodeAt(pos)
  return node ? { pos, index: $from.index(0), size: node.nodeSize } : null
}

// Позиция, куда блок встанет ПОСЛЕ удаления его самого. Считается от документа без него —
// иначе смещение при движении вниз уезжает ровно на размер перемещаемого блока.
function landing(state: EditorState, block: TopBlock, target: MoveTarget): number | null {
  const doc = state.doc
  const total = doc.childCount

  if (target === 'start') return block.index === 0 ? null : 0
  if (target === 'end') return block.index === total - 1 ? null : doc.content.size - block.size

  if (target === 'up') {
    if (block.index === 0) return null
    return block.pos - doc.child(block.index - 1).nodeSize
  }

  if (block.index === total - 1) return null
  return block.pos + doc.child(block.index + 1).nodeSize
}

function position(target: MoveTarget, block: TopBlock, total: number): number {
  if (target === 'start') return 1
  if (target === 'end') return total
  return (target === 'up' ? block.index - 1 : block.index + 1) + 1
}

export const BlockMoves = Extension.create<BlockMovesOptions>({
  name: 'blockMoves',

  addOptions() {
    return { onAnnounce: null }
  },

  addCommands() {
    return {
      moveBlock: (target) => ({ state, tr, dispatch }) => {
        const block = topBlock(state)
        if (!block) return false

        const to = landing(state, block, target)
        // Край документа — не ошибка, просто двигать некуда.
        if (to === null) return false

        if (dispatch) {
          const node = state.doc.nodeAt(block.pos)!
          tr.delete(block.pos, block.pos + block.size)
          tr.insert(to, node)
          tr.setSelection(TextSelection.near(tr.doc.resolve(to + 1)))
          tr.setMeta(FLASH, to)
          tr.scrollIntoView()

          const total = state.doc.childCount
          this.options.onAnnounce?.(position(target, block, total), total)
        }
        return true
      },
    }
  },

  addKeyboardShortcuts() {
    return {
      'Alt-ArrowUp': () => this.editor.commands.moveBlock('up'),
      'Alt-ArrowDown': () => this.editor.commands.moveBlock('down'),
      'Alt-Shift-ArrowUp': () => this.editor.commands.moveBlock('start'),
      'Alt-Shift-ArrowDown': () => this.editor.commands.moveBlock('end'),
    }
  },

  addProseMirrorPlugins() {
    return [moveFlash()]
  },
})

// ── Вспышка ───────────────────────────────────────────────────────────────────

function moveFlash(): Plugin<number | null> {
  return new Plugin<number | null>({
    key: FLASH,

    state: {
      init: () => null,
      apply(tr: Transaction, value: number | null): number | null {
        const set = tr.getMeta(FLASH)
        if (set !== undefined) return set as number | null
        // Позиция переезжает вместе с документом: пока горит вспышка, соседние правки не
        // должны сдвигать подсветку на чужой блок.
        return value === null ? null : tr.mapping.map(value)
      },
    },

    props: {
      decorations(state) {
        const pos = FLASH.getState(state)
        if (pos === null || pos === undefined) return null
        const node = state.doc.nodeAt(pos)
        if (!node) return null
        return DecorationSet.create(state.doc, [
          Decoration.node(pos, pos + node.nodeSize, { class: 'is-moved' }),
        ])
      },
    },

    // Гасит вспышку сам плагин: команда о таймерах знать не обязана, а перемещений подряд
    // может быть много — каждое следующее просто переставляет срок.
    view(view) {
      let timer: number | undefined
      return {
        update(updated) {
          const pos = FLASH.getState(updated.state)
          if (pos === null || pos === undefined) return
          window.clearTimeout(timer)
          timer = window.setTimeout(() => {
            if (!updated.isDestroyed) updated.dispatch(updated.state.tr.setMeta(FLASH, null))
          }, FLASH_MS)
        },
        destroy() {
          window.clearTimeout(timer)
        },
      }
    },
  })
}
