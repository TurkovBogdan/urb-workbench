// A list is one block with a flat row of items.
//
// "Nesting" here is a `depth` number on the item: Tab changes the number rather than rearranging
// nodes. Hence the schema's key property — one item maps onto one markdown line, and the
// serializer has nothing to fold. The price is everything the browser would otherwise do itself:
// numbering, markers and indents are computed here, because items of different levels sit side by
// side rather than in nested lists, and an `ol` would count them consecutively.
import { InputRule, Node, mergeAttributes } from '@tiptap/core'
import type { ChainedCommands, Editor } from '@tiptap/core'
import type { EditorState } from '@tiptap/pm/state'
import { Plugin, PluginKey, TextSelection } from '@tiptap/pm/state'
import { Decoration, DecorationSet } from '@tiptap/pm/view'
import type { Node as PMNode } from '@tiptap/pm/model'

// The shape of what Tiptap passes to an input rule handler; it does not export the full type.
interface InputRuleProps {
  state: EditorState
  range: { from: number; to: number }
  match: RegExpMatchArray
  chain: () => ChainedCommands
}

export interface ListKind {
  ordered: boolean
  /** `null` — a plain item; `true`/`false` — a checkbox item and its state. */
  checked: boolean | null
}

declare module '@tiptap/core' {
  interface Commands<ReturnType> {
    flatBlocks: {
      /** A prefixed name: `toggleList` is already taken by the @tiptap/extension-list types, and
       *  a declaration on top of it merges into a union instead of replacing it. */
      toggleFlatList: (kind: ListKind) => ReturnType
      indentListItem: () => ReturnType
      outdentListItem: () => ReturnType
    }
  }
}

// ── Item ──────────────────────────────────────────────────────────────────────

export const ListItem = Node.create({
  name: 'listItem',
  content: 'inline*',
  defining: true,

  addAttributes() {
    return {
      depth: {
        default: 0,
        parseHTML: (element) => Number(element.getAttribute('data-depth') ?? 0),
        // `--depth` goes to CSS as an indent: the level is the item's styling, not its place in
        // the structure.
        renderHTML: (attributes) => ({ 'data-depth': attributes.depth, style: `--depth:${attributes.depth}` }),
      },
      ordered: {
        default: false,
        parseHTML: (element) => element.getAttribute('data-ordered') === 'true',
        renderHTML: (attributes) => ({ 'data-ordered': String(Boolean(attributes.ordered)) }),
      },
      checked: {
        default: null,
        parseHTML: (element) => {
          const value = element.getAttribute('data-checked')
          return value === null ? null : value === 'true'
        },
        // The same class the renderer marks a checkbox item with: both zones take the document
        // typography from one file (`markdown/shared/document.css`), and they must match through
        // markup, not through two similar rule sets.
        renderHTML: (attributes) => (attributes.checked === null
          ? {}
          : { 'data-checked': String(attributes.checked), class: 'md-task' }),
      },
    }
  },

  parseHTML() {
    return [{ tag: 'li' }]
  },

  renderHTML({ HTMLAttributes }) {
    return ['li', mergeAttributes(HTMLAttributes), 0]
  },
})

// ── List ──────────────────────────────────────────────────────────────────────

export const List = Node.create({
  name: 'list',
  group: 'block',
  content: 'listItem+',

  parseHTML() {
    return [{ tag: 'ul[data-list]' }]
  },

  renderHTML({ HTMLAttributes }) {
    return ['ul', mergeAttributes(HTMLAttributes, { 'data-list': '' }), 0]
  },

  addCommands() {
    return {
      toggleFlatList: (kind) => ({ state, tr, dispatch }) => {
        const top = topBlock(state)
        if (!top) return false
        const { list, listItem, paragraph } = state.schema.nodes

        if (top.node.type === list) {
          const first = top.node.firstChild
          const sameKind = first !== null
            && first.attrs.ordered === kind.ordered
            && (first.attrs.checked === null) === (kind.checked === null)

          if (sameKind) {
            // Same kind — turn the list off: every item becomes a paragraph, and the levels are
            // lost along with the list, because a paragraph has nowhere to keep them.
            const blocks: PMNode[] = []
            top.node.forEach((item) => blocks.push(paragraph.create(null, item.content)))
            if (dispatch) tr.replaceWith(top.pos, top.pos + top.node.nodeSize, blocks)
            return true
          }

          // A different kind — rewrite the items' attributes without touching the content.
          if (dispatch) {
            let at = top.pos + 1
            top.node.forEach((item) => {
              tr.setNodeMarkup(at, undefined, {
                ...item.attrs,
                ordered: kind.ordered,
                checked: kind.checked === null ? null : (item.attrs.checked ?? false),
              })
              at += item.nodeSize
            })
          }
          return true
        }

        if (!top.node.isTextblock) return false
        if (dispatch) {
          const item = listItem.create({ depth: 0, ordered: kind.ordered, checked: kind.checked }, top.node.content)
          tr.replaceWith(top.pos, top.pos + top.node.nodeSize, list.create(null, item))
          tr.setSelection(TextSelection.near(tr.doc.resolve(top.pos + 2)))
        }
        return true
      },

      indentListItem: () => ({ state, tr, dispatch }) => shiftDepth(state, tr, dispatch, 1),
      outdentListItem: () => ({ state, tr, dispatch }) => shiftDepth(state, tr, dispatch, -1),
    }
  },

  // Markdown input rules. They left together with the disabled StarterKit nodes, and without them
  // a markdown editor stops understanding markdown: a typed `- ` stayed as text.
  addInputRules() {
    const toList = (kind: ListKind) => ({ state, chain, range }: InputRuleProps): void => {
      // Inside an item `- ` is just a hyphen. Without this check the rule would catch the item's
      // start and, with a same-kind command, DISSOLVE the list.
      if (itemAt(state)) return
      chain().deleteRange(range).toggleFlatList(kind).run()
    }

    return [
      new InputRule({ find: /^\s*[-+*]\s$/, handler: toList({ ordered: false, checked: null }) }),
      new InputRule({ find: /^\s*\d+[.)]\s$/, handler: toList({ ordered: true, checked: null }) }),
      // `- [ ] ` cannot be typed in one go: `- ` fires first. So the checkbox is set from inside
      // the item — exactly as Notion does it.
      new InputRule({
        find: /^\[([ xX])\]\s$/,
        handler: ({ state, chain, range, match }) => {
          const found = itemAt(state)
          if (!found) return
          const checked = match[1] !== ' '
          chain()
            .deleteRange(range)
            .command(({ tr }) => {
              tr.setNodeMarkup(found.pos, undefined, { ...found.node.attrs, checked })
              return true
            })
            .run()
        },
      }),
    ]
  },

  addKeyboardShortcuts() {
    return {
      Tab: () => this.editor.commands.indentListItem(),
      'Shift-Tab': () => this.editor.commands.outdentListItem(),
      Enter: () => exitOnEmptyItem(this.editor),
      Backspace: () => backspaceAtItemStart(this.editor),

      // The same shortcuts as the disabled StarterKit nodes: anyone who knows any other
      // Tiptap-based editor arrives here with muscle memory already in place.
      'Mod-Shift-8': () => this.editor.commands.toggleFlatList({ ordered: false, checked: null }),
      'Mod-Shift-7': () => this.editor.commands.toggleFlatList({ ordered: true, checked: null }),
      'Mod-Shift-9': () => this.editor.commands.toggleFlatList({ ordered: false, checked: false }),
    }
  },

  addProseMirrorPlugins() {
    return [listMarkers(), taskToggle()]
  },
})

// ── Positioning ───────────────────────────────────────────────────────────────

interface TopBlock { pos: number; node: PMNode }

function topBlock(state: EditorState): TopBlock | null {
  const { $from } = state.selection
  if ($from.depth < 1) return null
  const pos = $from.before(1)
  const node = state.doc.nodeAt(pos)
  return node ? { pos, node } : null
}

interface ItemRef {
  node: PMNode
  pos: number
  index: number
  list: PMNode
  listPos: number
}

function itemAt(state: EditorState): ItemRef | null {
  const { $from } = state.selection
  for (let depth = $from.depth; depth > 0; depth -= 1) {
    if ($from.node(depth).type.name !== 'listItem') continue
    return {
      node: $from.node(depth),
      pos: $from.before(depth),
      index: $from.index(depth - 1),
      list: $from.node(depth - 1),
      listPos: $from.before(depth - 1),
    }
  }
  return null
}

// ── Item level ────────────────────────────────────────────────────────────────

type Dispatch = ((args?: unknown) => void) | undefined

// A level cannot exceed the previous item's by more than one — otherwise a "nested" item with no
// parent would appear, and the list would stop rendering as a list.
function shiftDepth(state: EditorState, tr: EditorState['tr'], dispatch: Dispatch, delta: number): boolean {
  const found = itemAt(state)
  if (!found) return false

  const previous = found.index > 0 ? found.list.child(found.index - 1) : null
  const ceiling = previous ? Number(previous.attrs.depth) + 1 : 0
  const current = Number(found.node.attrs.depth)
  const next = Math.min(Math.max(current + delta, 0), ceiling)
  if (next === current) return false

  if (dispatch) {
    tr.setNodeMarkup(found.pos, undefined, { ...found.node.attrs, depth: next })
    // Items that were deeper follow along — otherwise they would come loose from their parent item.
    let at = found.pos + found.node.nodeSize
    for (let index = found.index + 1; index < found.list.childCount; index += 1) {
      const child = found.list.child(index)
      if (Number(child.attrs.depth) <= current) break
      tr.setNodeMarkup(at, undefined, { ...child.attrs, depth: Math.max(0, Number(child.attrs.depth) + (next - current)) })
      at += child.nodeSize
    }
  }
  return true
}

// ── Leaving the list ──────────────────────────────────────────────────────────

// Enter in an empty last item closes the list — the only way out of it without resorting to the
// mouse.
function exitOnEmptyItem(editor: Editor): boolean {
  const found = itemAt(editor.state)
  if (!found || found.node.content.size > 0) return false
  if (found.index !== found.list.childCount - 1) return false

  return editor.commands.command(({ tr, dispatch }) => {
    if (!dispatch) return true
    const paragraph = tr.doc.type.schema.nodes.paragraph

    if (found.list.childCount === 1) {
      tr.replaceWith(found.listPos, found.listPos + found.list.nodeSize, paragraph.create())
      tr.setSelection(TextSelection.near(tr.doc.resolve(found.listPos + 1)))
      return true
    }

    const after = found.listPos + found.list.nodeSize - found.node.nodeSize
    tr.delete(found.pos, found.pos + found.node.nodeSize)
    tr.insert(after, paragraph.create())
    tr.setSelection(TextSelection.near(tr.doc.resolve(after + 1)))
    return true
  })
}

// Backspace at the start of an item: first it outdents, and only on the very first item at level
// zero does it dissolve the list. That way deletion does not drop the text into the neighbouring
// block.
function backspaceAtItemStart(editor: Editor): boolean {
  const { selection } = editor.state
  if (!selection.empty || selection.$from.parentOffset !== 0) return false

  const found = itemAt(editor.state)
  if (!found) return false
  if (Number(found.node.attrs.depth) > 0) return editor.commands.outdentListItem()
  if (found.index !== 0) return false

  return editor.commands.toggleFlatList({
    ordered: Boolean(found.node.attrs.ordered),
    checked: found.node.attrs.checked as boolean | null,
  })
}

// ── Markers ───────────────────────────────────────────────────────────────────

const MARKERS = new PluginKey('flatListMarkers')

// An item's number is derived from the flat row, not a stored value: keeping it in an attribute
// would mean renumbering half the document on every Enter. CSS cannot count it on its own (the
// levels sit in one row, not in nested lists), so the number arrives as a decoration.
function listMarkers(): Plugin {
  return new Plugin({
    key: MARKERS,
    props: {
      decorations(state) {
        const decorations: Decoration[] = []

        state.doc.descendants((node, pos) => {
          if (node.type.name !== 'list') return false

          const counters: number[] = []
          let previousDepth = -1
          let at = pos + 1

          node.forEach((item) => {
            const depth = Number(item.attrs.depth)
            if (depth > previousDepth) counters[depth] = 0
            counters.length = depth + 1
            if (item.attrs.ordered) counters[depth] = (counters[depth] ?? 0) + 1
            else counters[depth] = 0
            previousDepth = depth

            const marker = item.attrs.checked !== null ? '' : item.attrs.ordered ? `${counters[depth]}.` : '•'
            decorations.push(Decoration.node(at, at + item.nodeSize, { 'data-marker': marker }))
            at += item.nodeSize
          })

          return false
        })

        return DecorationSet.create(state.doc, decorations)
      },
    },
  })
}

// ── Checkbox ──────────────────────────────────────────────────────────────────

// A click on the pseudo-element lands on the <li> itself, so only the coordinate tells the
// checkbox from the text: the boundary is the item's left padding, after which the content
// starts. It is read from computed styles, not a constant, or the nesting level would shift it.
function taskToggle(): Plugin {
  return new Plugin({
    props: {
      handleClick(view, _pos, event) {
        const target = event.target as HTMLElement | null
        const item = target?.closest?.('li[data-checked]')
        if (!item) return false
        if (event.offsetX > parseFloat(getComputedStyle(item).paddingLeft || '0')) return false

        const itemPos = view.posAtDOM(item, 0) - 1
        const node = view.state.doc.nodeAt(itemPos)
        if (!node || node.type.name !== 'listItem' || node.attrs.checked === null) return false

        view.dispatch(view.state.tr.setNodeMarkup(itemPos, undefined, { ...node.attrs, checked: !node.attrs.checked }))
        return true
      },
    },
  })
}
