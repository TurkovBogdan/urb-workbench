// Moving a block without dragging — and confirming that the move happened.
//
// The rollout order comes from research RESEARCH@0b534e01e9: the alternative path first, drag
// second. There are three reasons, all practical.
//
// 1. The standard. WCAG 2.2 SC 2.5.7 (AA) requires every drag outcome to have a single-pointer
//    path without dragging itself. Keyboard emulation of drag does NOT satisfy this criterion —
//    it specifically needs a pointer. Separately, SC 2.1.1 (A) requires the same action to be
//    operable from the keyboard. These are two different requirements, and one does not replace
//    the other: the menu covers the first, the shortcuts the second.
// 2. A safety net. While drag is unfinished, a block can still be moved.
// 3. Economy. The keyboard part rests on the same commands as the menu; had we built it after
//    drag, the handlers would have had to be rewritten twice.
//
// The `Alt+↑/↓` and `Alt+Shift+↑/↓` layout is borrowed from Linear, the reference analysed in the
// research. Holding keys is never required: SC 2.1.1 forbids timing on keystrokes.
import { Extension } from '@tiptap/core'
import type { EditorState, Transaction } from '@tiptap/pm/state'
import { Plugin, PluginKey, TextSelection } from '@tiptap/pm/state'
import { Decoration, DecorationSet } from '@tiptap/pm/view'

/** Where to move the block. `start` / `end` mean the start and end of the document. */
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

// A flash on the moved block: 700 ms is the value from Atlassian's design framework. It is needed
// because after a move the eye loses the object among its neighbours: the block has settled, but
// the user is not sure it settled where intended.
const FLASH_MS = 700
const FLASH = new PluginKey<number | null>('blockMoveFlash')

// ── Command ───────────────────────────────────────────────────────────────────

interface TopBlock { pos: number; index: number; size: number }

function topBlock(state: EditorState): TopBlock | null {
  const { $from } = state.selection
  // A caret inside the block is the usual case. Depth 0 is a whole-block selection: that is how
  // the handle selects it before opening the menu, and the command must understand both kinds.
  const pos = $from.depth >= 1 ? $from.before(1) : $from.pos
  const node = state.doc.nodeAt(pos)
  return node ? { pos, index: $from.index(0), size: node.nodeSize } : null
}

// The position the block lands at AFTER the block itself is deleted. Computed against the
// document without it — otherwise a move down is off by exactly the moved block's size.
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
        // The document edge is not an error, there is just nowhere to move.
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

// ── Flash ─────────────────────────────────────────────────────────────────────

function moveFlash(): Plugin<number | null> {
  return new Plugin<number | null>({
    key: FLASH,

    state: {
      init: () => null,
      apply(tr: Transaction, value: number | null): number | null {
        const set = tr.getMeta(FLASH)
        if (set !== undefined) return set as number | null
        // The position moves with the document: while the flash is lit, nearby edits must not
        // shift the highlight onto another block.
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

    // The plugin itself puts the flash out: the command need not know about timers, and there may
    // be many moves in a row — each next one simply resets the deadline.
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
