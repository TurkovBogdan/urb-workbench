// A code block's language, lifted onto the outer element.
//
// The language lives in a node attribute, but Tiptap puts it on `<code>` while the header is drawn
// by `<pre>`, and CSS cannot look upwards. A decoration copies the language onto `<pre>` — then
// the header appears by itself and disappears from a block without a language.
import { Plugin } from '@tiptap/pm/state'
import { Decoration, DecorationSet } from '@tiptap/pm/view'

export function codeLanguages(): Plugin {
  return new Plugin({
    props: {
      decorations(state) {
        const decorations: Decoration[] = []
        state.doc.descendants((node, pos) => {
          if (node.type.name !== 'codeBlock') return false
          decorations.push(Decoration.node(pos, pos + node.nodeSize, {
            'data-language': String(node.attrs.language ?? ''),
          }))
          return false
        })
        return DecorationSet.create(state.doc, decorations)
      },
    },
  })
}
