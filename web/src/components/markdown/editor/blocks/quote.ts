// A quote is a line block, not a container.
//
// In the default ProseMirror tree a blockquote holds paragraphs inside, and a multi-line quote
// becomes yet another shape of the same content. Here a multi-line quote is several adjacent
// blocks sharing one flag, and each still maps onto a single markdown line.
import { InputRule, Node, mergeAttributes } from '@tiptap/core'

export const Quote = Node.create({
  name: 'quote',
  group: 'block',
  content: 'inline*',
  defining: true,

  parseHTML() {
    return [{ tag: 'blockquote' }]
  },

  renderHTML({ HTMLAttributes }) {
    return ['blockquote', mergeAttributes(HTMLAttributes), 0]
  },

  // The same shortcut as the disabled StarterKit blockquote — but registered in BOTH cases. With
  // Shift held the browser reports `key: "B"`, and a binding written in lowercase never fires: a
  // long-standing trap in Tiptap itself, verified in the browser. Digits cannot be handled this
  // way — there the fallback match on the key code saves the day.
  addKeyboardShortcuts() {
    const toQuote = () => this.editor.commands.toggleNode(this.name, 'paragraph')
    return { 'Mod-Shift-b': toQuote, 'Mod-Shift-B': toQuote }
  },

  // Disabling the StarterKit blockquote took its input rule with it: `> ` stopped starting a quote
  // and stayed a literal, which the serializer then escaped into `\>`.
  addInputRules() {
    return [
      new InputRule({
        find: /^\s*>\s$/,
        handler: ({ chain, range }) => {
          chain().deleteRange(range).setNode(this.name).run()
        },
      }),
    ]
  },
})
