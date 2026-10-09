// A mermaid diagram as an editor block: shown drawn, edited as source.
//
// In markdown a diagram is a fence tagged `mermaid`, and that stays the only way it is stored —
// the renderer draws exactly that fence, so a body edited here reads the same everywhere else.
// In the document it is a node of its own rather than a code block with a language: a code block
// is text the caret walks through, while a diagram is a picture first and its source second.
//
// It is an atom with the source in an attribute, not a node with text content. With text content
// the source would be ProseMirror's own text — character-level undo, but also a hidden editable
// region to show and hide around the picture, which breaks under drag and block moves. Here the
// source is edited in an ordinary field inside the view and written back whole; ProseMirror sees
// one attribute change per edit and never a caret inside the block.
import { Node, mergeAttributes } from '@tiptap/core'
import { VueNodeViewRenderer } from '@tiptap/vue-3'
import DiagramView from './DiagramView.vue'
import { DIAGRAM_LANGUAGE } from '../../shared/contracts'

/** What `/` inserts: the smallest diagram that draws, so the preview is not an error from the start. */
const STARTER = 'flowchart LR\n  A --> B'

declare module '@tiptap/core' {
  interface Commands<ReturnType> {
    diagram: {
      /** Insert a diagram with a starter source and open it for editing at once. */
      insertDiagram: () => ReturnType
    }
  }
  interface Storage {
    diagram: DiagramStorage
  }
}

export interface DiagramStorage {
  /**
   * The next diagram view to mount opens in edit mode. Set by `insertDiagram` and taken by the
   * view that mounts right after it — the only one created by that transaction. A flag rather than
   * a node attribute: "being edited" is a state of the screen, not of the document, and an
   * attribute would ride into undo history and into every copy of the block.
   */
  openNext: boolean
}

export const Diagram = Node.create<Record<string, never>, DiagramStorage>({
  name: 'diagram',
  group: 'block',
  atom: true,
  selectable: true,
  draggable: false,

  addStorage() {
    return { openNext: false }
  },

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
      // The source field and the view's buttons are the view's own: a key typed there must not
      // reach ProseMirror's keymap (Enter would split the document, Backspace delete the block),
      // and a double click on the picture opens the fullscreen viewer instead of selecting a word.
      stopEvent: ({ event }) => {
        const target = event.target as HTMLElement | null
        if (event.type === 'dblclick') return true
        return Boolean(target?.closest('textarea, button'))
      },
    })
  },

  addCommands() {
    return {
      insertDiagram: () => ({ commands }) => {
        this.storage.openNext = true
        return commands.insertContent({ type: this.name, attrs: { source: STARTER } })
      },
    }
  },
})
