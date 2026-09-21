// Язык блока кода — на внешний элемент.
//
// Язык лежит в атрибуте узла, но Tiptap кладёт его на `<code>`, а шапку рисует `<pre>`, и
// смотреть снизу вверх CSS не умеет. Декорация переносит язык на `<pre>` — тогда шапка
// появляется сама и исчезает у блока без языка.
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
