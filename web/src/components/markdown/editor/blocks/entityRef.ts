// Entity reference as an editor node — the project's own construct, carried through every
// layer a custom handler has to touch: schema, input rule, paste rule, command, node view and
// both directions of the markdown bridge.
//
// It is an atom: the caret never lands inside a hash and turns `TASK@1a2b3c4d5e` into a dead
// half-code. The code is still replaceable — through the pill's own edit field (`EntityRefView`),
// which swaps the whole code at once and refuses anything that is not one.
import { InputRule, Node, mergeAttributes, nodePasteRule } from '@tiptap/core'
import { NodeSelection } from '@tiptap/pm/state'
import { VueNodeViewRenderer } from '@tiptap/vue-3'
import EntityRefView from './EntityRefView.vue'
import { canonicalCode, REF_CODE } from '../../shared/contracts'

// Enter on a selected pill opens its edit field. The keymap sees the selection, the node view owns
// the field, so the request travels as a DOM event on the pill itself.
export const REF_EDIT_EVENT = 'md-ref-edit'

// One definition of «what is a code» for the renderer, the parser and the editor. A second
// pattern here would mean a body where a pill renders but cannot be typed, or the reverse.
const TYPED_CODE = new RegExp(`${REF_CODE.source}$`, 'i')
const PASTED_CODE = new RegExp(REF_CODE.source, 'gi')

declare module '@tiptap/core' {
  interface Commands<ReturnType> {
    entityRef: {
      insertEntityRef: (code: string) => ReturnType
    }
  }
}

export const EntityRef = Node.create({
  name: 'entityRef',
  // Above the default 100: Enter on a selected pill must reach this keymap before the one that
  // splits the paragraph.
  priority: 101,
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

  addKeyboardShortcuts() {
    return {
      Enter: ({ editor }) => {
        const { selection } = editor.state
        if (!(selection instanceof NodeSelection) || selection.node.type.name !== this.name) return false
        editor.view.nodeDOM(selection.from)?.dispatchEvent(new CustomEvent(REF_EDIT_EVENT))
        return true
      },
    }
  },

  // Typing the last hex character of a code turns it into a pill in place — the same moment
  // the renderer would have recognised it.
  //
  // Written out rather than built with `nodeInputRule`: that helper treats a first capture
  // group as «the part to replace» and inserts the last typed character separately, and the
  // shared REF_CODE pattern captures the type word. Through the helper `TASK@1a2b3c4d5e`
  // came back as `TASK@1a2b3c4d5e@1a2b3c4d5e`. Replacing the matched range outright has no
  // such convention to collide with.
  addInputRules() {
    return [
      new InputRule({
        find: TYPED_CODE,
        handler: ({ state, range, match }) => {
          state.tr.replaceWith(range.from, range.to, this.type.create({ code: canonicalCode(match[0]) }))
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
        getAttributes: (match) => ({ code: canonicalCode(match[0]) }),
      }),
    ]
  },
})
