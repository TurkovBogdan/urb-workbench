// A mermaid diagram as an editor block: shown drawn, edited as source.
//
// In markdown a diagram is a fence tagged `mermaid`, and that stays the only way it is stored —
// the renderer draws exactly that fence, so a body edited here reads the same everywhere else.
//
// At rest it is a node of its own, an atom with the source in an attribute: a picture first, which
// the caret does not walk into and a drag carries whole. To be edited it TURNS INTO the editor's
// code block with the language `mermaid` — the same fence in markdown, so nothing stored changes —
// and gets everything that block has: highlighting, line numbers, Tab over lines, character-level
// undo. When the caret leaves that block, or on Esc or "Done", it turns back into the picture.
// An emptied source removes the block: an empty diagram draws nothing.
//
// So a mermaid code block in a field with diagrams is a diagram being edited, whatever made it: the
// "Edit" button, the slash menu, or a fence typed by hand.
import { Node, mergeAttributes, type Editor } from '@tiptap/core'
import { VueNodeViewRenderer } from '@tiptap/vue-3'
import { NodeSelection, Plugin, PluginKey, TextSelection, type EditorState, type Transaction } from '@tiptap/pm/state'
import type { Node as PMNode } from '@tiptap/pm/model'
import DiagramView from './DiagramView.vue'
import { DIAGRAM_LANGUAGE } from '../../shared/contracts'

/** What `/` inserts: the smallest diagram that draws, so the preview is not an error from the start. */
const STARTER = 'flowchart LR\n  A --> B'

declare module '@tiptap/core' {
  interface Commands<ReturnType> {
    diagram: {
      /** Insert a diagram with a starter source, opened for editing at once. */
      insertDiagram: () => ReturnType
      /** Turn the diagram at `pos` into its source, a mermaid code block, with the caret inside. */
      editDiagram: (pos: number) => ReturnType
      /** Turn the mermaid code block at `pos` back into a diagram, selected. */
      finishDiagram: (pos: number) => ReturnType
    }
  }
}

/** A diagram being edited: a code block whose language is the diagram fence's. */
export function isDiagramSource(node: PMNode): boolean {
  return node.type.name === 'codeBlock' && node.attrs.language === DIAGRAM_LANGUAGE
}

/**
 * Replace the source block at `pos` with what it stands for: a diagram, or nothing when the
 * source is empty. Returns the diagram's position, `null` when the block was removed.
 */
function settle(tr: Transaction, pos: number, block: PMNode): number | null {
  const source = block.textContent
  if (!source.trim()) {
    tr.delete(pos, pos + block.nodeSize)
    return null
  }
  const diagram = tr.doc.type.schema.nodes.diagram!.create({ source })
  tr.replaceWith(pos, pos + block.nodeSize, diagram)
  return pos
}

/** Source blocks the caret is not in, last first — so settling one leaves the others' positions. */
function abandonedSources(state: EditorState): Array<{ pos: number; node: PMNode }> {
  const head = state.selection.$head.pos
  const found: Array<{ pos: number; node: PMNode }> = []
  state.doc.forEach((node, pos) => {
    if (!isDiagramSource(node)) return
    if (head >= pos && head <= pos + node.nodeSize) return
    found.push({ pos, node })
  })
  return found.reverse()
}

function sourceBlockAtCaret(editor: Editor): number | null {
  const { $from } = editor.state.selection
  if ($from.depth < 1) return null
  const pos = $from.before(1)
  const node = editor.state.doc.nodeAt(pos)
  return node && isDiagramSource(node) ? pos : null
}

const SETTLE = new PluginKey('diagramSettle')

export const Diagram = Node.create({
  name: 'diagram',
  group: 'block',
  atom: true,
  selectable: true,
  draggable: false,

  // In HTML — the clipboard, a drag between fields — the block travels as the code block it is in
  // markdown: `<pre><code class="language-mermaid">source</code></pre>`. A field without diagrams
  // then reads it as a mermaid code block, a field without code blocks as plain text, and the
  // source survives either way; as a bare `div` it was dropped by such a field, while the
  // drag removed it from where it came from.
  addAttributes() {
    return {
      source: {
        default: '',
        parseHTML: (element) => element.textContent ?? '',
        rendered: false,
      },
    }
  },

  parseHTML() {
    return [
      { tag: 'pre[data-diagram]' },
      // A mermaid listing from elsewhere — a rendered page, another editor — becomes a diagram too.
      // Above the code block's own rule, which would otherwise take every `pre`.
      {
        tag: 'pre',
        priority: 60,
        getAttrs: (element) => (element.querySelector(`code.language-${DIAGRAM_LANGUAGE}`) ? null : false),
      },
    ]
  },

  renderHTML({ node, HTMLAttributes }) {
    return [
      'pre',
      mergeAttributes({ 'data-diagram': '' }, HTMLAttributes),
      ['code', { class: `language-${DIAGRAM_LANGUAGE}` }, String(node.attrs.source ?? '')],
    ]
  },

  // Copied as plain text, the block is what it is in the body — a fence.
  renderText({ node }) {
    return `\`\`\`${DIAGRAM_LANGUAGE}\n${String(node.attrs.source ?? '')}\n\`\`\``
  },

  addNodeView() {
    return VueNodeViewRenderer(DiagramView, {
      // The view's buttons are its own, and a double click on the picture opens the fullscreen
      // viewer instead of selecting a word.
      stopEvent: ({ event }) => {
        const target = event.target as HTMLElement | null
        if (event.type === 'dblclick') return true
        return Boolean(target?.closest('button'))
      },
    })
  },

  addCommands() {
    return {
      insertDiagram: () => ({ state, tr, dispatch }) => {
        const codeBlock = state.schema.nodes.codeBlock
        if (!codeBlock) return false
        if (dispatch) {
          const block = codeBlock.create({ language: DIAGRAM_LANGUAGE }, state.schema.text(STARTER))
          const { $from } = tr.selection
          // An empty top-level line (where `/` is usually typed) becomes the block; anywhere else
          // the block goes after the current top-level block.
          const onEmptyLine = $from.depth === 1 && $from.parent.isTextblock && $from.parent.content.size === 0
          const at = onEmptyLine ? $from.before(1) : $from.after(1)
          if (onEmptyLine) tr.replaceWith(at, $from.after(1), block)
          else tr.insert(at, block)
          tr.setSelection(TextSelection.create(tr.doc, at + 1 + STARTER.length)).scrollIntoView()
        }
        return true
      },

      editDiagram: (pos) => ({ state, tr, dispatch }) => {
        const node = state.doc.nodeAt(pos)
        const codeBlock = state.schema.nodes.codeBlock
        if (!node || node.type.name !== this.name || !codeBlock) return false
        if (dispatch) {
          const source = String(node.attrs.source ?? '')
          const block = codeBlock.create({ language: DIAGRAM_LANGUAGE }, source ? state.schema.text(source) : null)
          tr.replaceWith(pos, pos + node.nodeSize, block)
          tr.setSelection(TextSelection.create(tr.doc, pos + 1 + source.length)).scrollIntoView()
        }
        return true
      },

      finishDiagram: (pos) => ({ state, tr, dispatch }) => {
        const node = state.doc.nodeAt(pos)
        if (!node || !isDiagramSource(node)) return false
        if (dispatch) {
          const diagram = settle(tr, pos, node)
          if (diagram !== null) tr.setSelection(NodeSelection.create(tr.doc, diagram))
          tr.scrollIntoView()
        }
        return true
      },
    }
  },

  addKeyboardShortcuts() {
    return {
      Escape: () => {
        const pos = sourceBlockAtCaret(this.editor)
        return pos !== null && this.editor.commands.finishDiagram(pos)
      },
    }
  },

  // Leaving the source block — by click, arrow key, a block move — settles it into a diagram on the
  // same transaction that moved the caret away.
  addProseMirrorPlugins() {
    return [
      new Plugin({
        key: SETTLE,
        appendTransaction(transactions, _old, state) {
          if (!transactions.some((tr) => tr.docChanged || tr.selectionSet)) return null
          const abandoned = abandonedSources(state)
          if (!abandoned.length) return null
          const tr = state.tr
          for (const { pos, node } of abandoned) settle(tr, pos, node)
          return tr
        },
      }),
    ]
  },
})
