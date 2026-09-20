// Entity reference as an editor node — the project's own construct, carried through every
// layer a custom handler has to touch: schema, input rule, paste rule, command, node view and
// both directions of the markdown bridge.
//
// It is an atom: a code has no editable interior, and treating it as one is what stops a
// caret landing inside a hash and turning `AREA@1a2b3c4d5e` into a dead half-code.
import { InputRule, Node, mergeAttributes, nodePasteRule } from '@tiptap/core'
import { VueNodeViewRenderer } from '@tiptap/vue-3'
import EntityRefView from './EntityRefView.vue'
import { REF_CODE } from '../render'

// One definition of «what is a code» for the renderer, the parser and the editor. A second
// pattern here would mean a body where a pill renders but cannot be typed, or the reverse.
const TYPED_CODE = new RegExp(`${REF_CODE.source}$`)
const PASTED_CODE = new RegExp(REF_CODE.source, 'g')

declare module '@tiptap/core' {
  interface Commands<ReturnType> {
    entityRef: {
      insertEntityRef: (code: string) => ReturnType
    }
  }
}

export const EntityRef = Node.create({
  name: 'entityRef',
  group: 'inline',
  inline: true,
  atom: true,
  selectable: true,

  addAttributes() {
    return {
      code: {
        default: '',
        parseHTML: (element) => element.getAttribute('data-code') ?? '',
        renderHTML: (attributes) => ({ 'data-code': attributes.code }),
      },
    }
  },

  parseHTML() {
    return [{ tag: 'span[data-entity-ref]' }]
  },

  renderHTML({ HTMLAttributes, node }) {
    return ['span', mergeAttributes({ 'data-entity-ref': '', class: 'md-ref' }, HTMLAttributes), node.attrs.code]
  },

  addNodeView() {
    return VueNodeViewRenderer(EntityRefView)
  },

  addCommands() {
    return {
      insertEntityRef: (code) => ({ commands }) => commands.insertContent({ type: this.name, attrs: { code } }),
    }
  },

  // Typing the last hex character of a code turns it into a pill in place — the same moment
  // the renderer would have recognised it.
  //
  // Written out rather than built with `nodeInputRule`: that helper treats a first capture
  // group as «the part to replace» and inserts the last typed character separately, and the
  // shared REF_CODE pattern captures the type word. Through the helper `NOTE@1a2b3c4d5e`
  // came back as `NOTE@1a2b3c4d5e@1a2b3c4d5e`. Replacing the matched range outright has no
  // such convention to collide with.
  addInputRules() {
    return [
      new InputRule({
        find: TYPED_CODE,
        handler: ({ state, range, match }) => {
          state.tr.replaceWith(range.from, range.to, this.type.create({ code: match[0] }))
        },
      }),
    ]
  },

  // Codes arrive pasted far more often than typed — out of a tool result, a chat, another body.
  addPasteRules() {
    return [
      nodePasteRule({
        find: PASTED_CODE,
        type: this.type,
        getAttributes: (match) => ({ code: match[0] }),
      }),
    ]
  },
})
