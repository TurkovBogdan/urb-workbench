// The code block: StarterKit's one is switched off and this takes its place under the same schema
// name and attribute (`codeBlock`, `language`), so the markdown bridge, `restrict` and the slash
// menu's `toggleCodeBlock` work on it unchanged. What it adds: a Vue view with the viewer's frame
// (language picker, line numbers, copy) and shiki highlighting over the text being edited.
//
// Text content, not an atom like the diagram: the caret walks through the code, undo works per
// character, and the view only frames what ProseMirror renders into `NodeViewContent`.
import { Node, mergeAttributes, textblockTypeInputRule, type Editor } from '@tiptap/core'
import { VueNodeViewRenderer } from '@tiptap/vue-3'
import { exitCode } from '@tiptap/pm/commands'
import CodeBlockView from './CodeBlockView.vue'
import { codeHighlight, type HighlightStats } from './codeHighlight'
import { DIAGRAM_LANGUAGE } from '../../shared/contracts'

const INDENT = '  '
// Both CommonMark fences, ``` and ~~~, open a block — with a space after the language, as an
// input rule, or with Enter on a line that holds only the fence.
const FENCE_INPUT = /^(?:```|~~~)([\w+-]*)[\s\n]$/
const FENCE_LINE = /^(?:```|~~~)([\w+-]*)$/

/**
 * Indent or outdent every line the selection touches, inside one code block. A line the selection
 * only reaches at its very start is left alone, as editors do. Outdenting takes one indent, a tab
 * or a lone space — whatever the line starts with; a line starting with none of them stays.
 */
function shiftLines(editor: Editor, direction: 'in' | 'out'): boolean {
  const { state, view } = editor
  const { $from, $to } = state.selection
  // A selection leaving the block is not this block's to shift — and swallowing Tab is kinder
  // than letting it replace the selection.
  if ($from.parent !== $to.parent) return true

  const text = $from.parent.textContent
  const base = $from.start()
  const first = text.lastIndexOf('\n', $from.parentOffset - 1) + 1
  const starts = [first]
  for (let i = first; i < $to.parentOffset - 1; i++) {
    if (text[i] === '\n') starts.push(i + 1)
  }

  const tr = state.tr
  // From the last line up, so the positions of the lines above stay valid.
  for (const start of [...starts].reverse()) {
    if (direction === 'in') {
      // An empty line in a shifted range stays empty, not two trailing spaces.
      const empty = start === text.length || text[start] === '\n'
      if (!empty || starts.length === 1) tr.insertText(INDENT, base + start)
      continue
    }
    const width = text.startsWith(INDENT, start) ? INDENT.length : /[\t ]/.test(text[start] ?? '') ? 1 : 0
    if (width) tr.delete(base + start, base + start + width)
  }
  if (tr.docChanged) view.dispatch(tr)
  return true
}

export interface CodeBlockOptions {
  /** Timing of each highlight pass — read by the diagnostics stand, unset everywhere else. */
  onStats?: (stats: HighlightStats) => void
}

export const CodeBlock = Node.create<CodeBlockOptions>({
  name: 'codeBlock',
  group: 'block',
  content: 'text*',
  marks: '',
  code: true,
  defining: true,

  addOptions() {
    return { onStats: undefined }
  },

  addAttributes() {
    return {
      language: {
        default: '',
        parseHTML: (element) => {
          const code = element.querySelector('code')
          const match = /language-([\w+-]+)/.exec(code?.className ?? '')
          return match?.[1] ?? ''
        },
        rendered: false,
      },
    }
  },

  parseHTML() {
    return [{ tag: 'pre', preserveWhitespace: 'full' }]
  },

  renderHTML({ node, HTMLAttributes }) {
    const language = String(node.attrs.language ?? '')
    return ['pre', mergeAttributes(HTMLAttributes), ['code', language ? { class: `language-${language}` } : {}, 0]]
  },

  addNodeView() {
    return VueNodeViewRenderer(CodeBlockView, {
      // The header's controls are the view's own; typing in the code itself goes to ProseMirror.
      stopEvent: ({ event }) => Boolean((event.target as HTMLElement | null)?.closest('.code-node__header')),
    })
  },

  // The command names StarterKit's block declares — the slash menu calls `toggleCodeBlock`, and
  // their types come with StarterKit, so nothing is re-declared here.
  addCommands() {
    return {
      setCodeBlock: (attributes) => ({ commands }) => commands.setNode(this.name, attributes),
      toggleCodeBlock: (attributes) => ({ commands }) => commands.toggleNode(this.name, 'paragraph', attributes),
    }
  },

  addInputRules() {
    return [textblockTypeInputRule({ find: FENCE_INPUT, type: this.type, getAttributes: (match) => ({ language: match[1] }) })]
  },

  addKeyboardShortcuts() {
    const inCode = (): boolean => this.editor.isActive(this.name)
    return {
      // The shortcut the slash menu advertises for this block. Not in a diagram's source: toggling
      // would turn the diagram into a paragraph of mermaid text (its type is fixed, see diagram.ts).
      'Mod-Alt-c': () => {
        const parent = this.editor.state.selection.$from.parent
        const isDiagramSource = parent.type.name === this.name
          && parent.attrs.language === DIAGRAM_LANGUAGE
          && Boolean(this.editor.schema.nodes.diagram)
        return isDiagramSource || this.editor.commands.toggleCodeBlock()
      },
      Enter: () => {
        const { $from, empty } = this.editor.state.selection
        if (!empty || $from.parent.type.name !== 'paragraph') return false
        if ($from.parentOffset !== $from.parent.content.size) return false
        const match = FENCE_LINE.exec($from.parent.textContent)
        if (!match) return false
        return this.editor
          .chain()
          .deleteRange({ from: $from.start(), to: $from.end() })
          .setNode(this.name, { language: match[1] })
          .run()
      },
      // A caret gets an indent; a selection shifts every line it touches, as in a code editor —
      // replacing the selection with two spaces deleted the selected lines.
      Tab: () => {
        if (!inCode()) return false
        if (this.editor.state.selection.empty) return this.editor.commands.insertContent(INDENT)
        return shiftLines(this.editor, 'in')
      },
      'Shift-Tab': () => inCode() && shiftLines(this.editor, 'out'),
      // Leaving the block: Mod-Enter anywhere, or ArrowDown on its last line when nothing follows.
      // Not three Enters, as StarterKit's block does: two blank lines are ordinary Python (PEP 8
      // between top-level definitions), and the third Enter threw the caret out mid-listing.
      'Mod-Enter': () => inCode() && this.editor.commands.command(({ state, dispatch }) => exitCode(state, dispatch)),
      ArrowDown: () => {
        if (!inCode()) return false
        const { state } = this.editor
        const { $from, empty } = state.selection
        const onLastLine = !$from.parent.textContent.slice($from.parentOffset).includes('\n')
        const isLastBlock = $from.after() === state.doc.content.size
        if (!empty || !onLastLine || !isLastBlock) return false
        return this.editor.commands.command(({ state: current, dispatch }) => exitCode(current, dispatch))
      },
      // Backspace in an empty block turns it back into a paragraph.
      Backspace: () => {
        if (!inCode()) return false
        const { $from, empty } = this.editor.state.selection
        if (!empty || $from.parent.textContent.length) return false
        return this.editor.commands.clearNodes()
      },
    }
  },

  addProseMirrorPlugins() {
    return [codeHighlight(this.options.onStats)]
  },
})
