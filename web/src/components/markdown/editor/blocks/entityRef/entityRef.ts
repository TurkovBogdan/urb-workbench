// Entity reference as an editor node — the project's own construct, carried through every
// layer a custom handler has to touch: schema, input rule, paste rule, command, node view and
// both directions of the markdown bridge.
//
// It is an atom: the caret never lands inside a hash and turns `TASK@1a2b3c4d5e` into a dead
// half-code. A pill is not edited in place — a wrong one is deleted whole and typed again.
//
// With `images` an `IMAGE@` code is drawn as the picture itself (`EntityImageView.vue`), the way
// the viewer draws it; the node stays the same reference, so the bridge, the clipboard and the
// stored text do not know the difference.
//
// The viewer wraps a gallery in a block of its own; a document cannot wrap inline nodes, so the
// same layout is drawn with decorations (`pictureLayout`): each picture gets its gallery's classes
// (column count, alone or not), the space after a picture is drawn as the gallery's gap — a real
// space the caret stands in — while the other blanks around a run are drawn at no width, a widget
// breaks the line ahead of a run and after it, and another ahead of each row of a gallery.
// The sizes of the pictures in their rows are set by the plugin's view (`layOutGalleries`). The
// text stays one paragraph, as stored. A picture is moved by dragging it (`pictureDrag.ts`) or with
// Alt+←/→ along its gallery (`pictureMove.ts`).
import { InputRule, Node, PasteRule, mergeAttributes } from '@tiptap/core'
import type { Mark as ProseMirrorMark, Node as ProseMirrorNode } from '@tiptap/pm/model'
import { NodeSelection, Plugin, PluginKey, Selection, TextSelection } from '@tiptap/pm/state'
import { Decoration, DecorationSet, type EditorView } from '@tiptap/pm/view'
import { VueNodeViewRenderer } from '@tiptap/vue-3'
import { nextTick, watch } from 'vue'
import EntityImageView from './EntityImageView.vue'
import EntityRefView from './EntityRefView.vue'
import { inlineChildren, isImageCode, pictureLayout, type PictureBreak } from './imageRuns'
import { pictureDrag, posOfTile } from './pictureDrag'
import { stepPicture, type GalleryPlace } from './pictureMove'
import { OPEN_PICTURE_EVENT } from './pictureViewer'
import { canonicalCode, REF_CODE } from '../../../shared/contracts'
import { galleryVersion, layOutGallery, ratioOf } from '../../../shared/pictures'

export interface EntityRefOptions {
  /** `IMAGE@` codes are pictures, not pills — the field's `image` feature. */
  images: boolean
  /** A picture moved with Alt+←/→: its place in the gallery now, for the live region. */
  onAnnounce: ((place: GalleryPlace) => void) | null
  /** A picture is being dragged (`pictureDrag.ts`). */
  onDragging: ((on: boolean) => void) | null
}

function lineBreak(spot: PictureBreak): () => HTMLElement {
  return () => {
    const element = document.createElement('span')
    element.className = `md-image-break${spot.single ? ' md-image-break--single' : ''}`
    element.setAttribute('aria-hidden', 'true')
    return element
  }
}

// Chrome draws no caret ahead of an uneditable picture that opens a line: there is nothing for the
// caret to stand after. ProseMirror ends such a line with an empty image for the same reason
// (`ProseMirror-separator`); this one opens it. Raw, so it stays editable content the caret sits by.
function caretHold(): HTMLElement {
  const image = document.createElement('img')
  image.className = 'ProseMirror-separator'
  image.alt = ''
  return image
}

// The other end of the line. ProseMirror puts the caret after a picture that closes a line right
// against the picture, and Chrome draws it at the picture's very edge — under the picture, which is
// painted over the text: only its tips above and below showed, and read as a caret on the next
// line. The caret is put after this zero-width space instead, past the picture's gap, where it shows
// as after a word. Uneditable, as every widget is: nothing typed lands in it.
function caretTail(): HTMLElement {
  const tail = document.createElement('span')
  tail.className = 'md-image-tail'
  tail.textContent = String.fromCharCode(0x200b)
  tail.setAttribute('aria-hidden', 'true')
  return tail
}

function pictureDecorations(doc: ProseMirrorNode): DecorationSet {
  const decorations: Decoration[] = []
  doc.descendants((node, pos) => {
    if (!node.isTextblock) return true
    const starts: number[] = []
    node.forEach((_child, offset) => starts.push(pos + 1 + offset))
    const layout = pictureLayout(inlineChildren(node), ratioOf)
    for (const { index, classes } of layout.pictures) {
      decorations.push(Decoration.node(starts[index], starts[index] + 1, { class: classes.join(' ') }))
    }
    for (const { index, from, to } of layout.spaces) {
      decorations.push(Decoration.inline(starts[index] + from, starts[index] + to, { class: 'md-image-space' }))
    }
    for (const { index, from, to } of layout.gaps) {
      const child = node.child(index)
      if (!child.isText) decorations.push(Decoration.node(starts[index], starts[index] + child.nodeSize, { class: 'md-image-gap' }))
      else if (to > from) decorations.push(Decoration.inline(starts[index] + from, starts[index] + to, { class: 'md-image-gap' }))
    }
    for (const index of layout.lineStarts) {
      decorations.push(Decoration.widget(starts[index], caretHold, { side: -1, key: 'md-image-caret-hold', raw: true }))
    }
    // Ahead of the caret (`side: -1`): the caret is drawn after it.
    for (const index of layout.lineEnds) {
      decorations.push(Decoration.widget(starts[index] + 1, caretTail, { side: -1, key: 'md-image-caret-tail', ignoreSelection: true }))
    }
    // The caret at a break stays with the text: ahead of a run it is drawn at the end of the text
    // line (the widget after it), after a run at the start of the next text line.
    for (const spot of layout.breaks) {
      decorations.push(Decoration.widget(starts[spot.index] + spot.offset, lineBreak(spot), {
        side: spot.before ? 1 : -1,
        key: `md-image-break-${spot.before ? 'before' : 'after'}-${spot.single ? 'single' : 'run'}`,
        ignoreSelection: true,
      }))
    }
    // The caret ahead of a row's first picture stays at the end of the row above, after its space:
    // put after the widget, it would stand ahead of an uneditable picture, and Chrome draws such a
    // caret after the picture instead.
    for (const row of layout.rows) {
      decorations.push(Decoration.widget(starts[row.index], () => rowBreak(row.classes), {
        side: 1,
        key: row.classes,
        ignoreSelection: true,
      }))
    }
    return false
  })
  return DecorationSet.create(doc, decorations)
}

function rowBreak(classes: string): HTMLElement {
  const element = document.createElement('span')
  element.className = classes
  element.setAttribute('aria-hidden', 'true')
  return element
}

// The proportions of a gallery's pictures are known only once they load, and only the drawn
// document holds both the pictures of a run and their loaded <img>: the gallery is laid out here,
// after every change of the document and every newly loaded picture (`shared/pictures.ts`).
function layOutGalleries(view: EditorView): void {
  view.state.doc.descendants((node, pos) => {
    if (!node.isTextblock) return true
    const starts: number[] = []
    node.forEach((_child, offset) => starts.push(pos + 1 + offset))
    for (const run of pictureLayout(inlineChildren(node)).runs) {
      const tiles = run.map((index) => view.nodeDOM(starts[index])).filter((dom): dom is HTMLElement => dom instanceof HTMLElement)
      layOutGallery(tiles)
    }
    return false
  })
}

const PICTURE_LAYOUT = new PluginKey<DecorationSet>('pictureLayout')

const hasPictures = (block: ProseMirrorNode): boolean => {
  let found = false
  block.forEach((child) => {
    if (child.type.name === 'entityRef' && isImageCode(String(child.attrs.code ?? ''))) found = true
  })
  return found
}

const isLowSurrogate = (code: number): boolean => code >= 0xdc00 && code <= 0xdfff
const isHighSurrogate = (code: number): boolean => code >= 0xd800 && code <= 0xdbff

// The caret steps left and right through a paragraph with pictures by the document, not by the
// browser: the browser cannot cross the line breaks and the blanks drawn at no width around a
// gallery, and stood still at the start of the text after one. A picture is selected on the way,
// as everywhere else; the edges of the paragraph are left to the editor.
function stepAroundPictures(view: EditorView, event: KeyboardEvent): boolean {
  if (event.key !== 'ArrowLeft' && event.key !== 'ArrowRight') return false
  if (event.shiftKey || event.altKey || event.ctrlKey || event.metaKey) return false
  const back = event.key === 'ArrowLeft'
  const { state } = view
  const { selection } = state
  const at = back ? selection.$from : selection.$to
  if (!at.parent.isTextblock || !hasPictures(at.parent)) return false
  if (selection instanceof NodeSelection) {
    view.dispatch(state.tr.setSelection(TextSelection.create(state.doc, back ? selection.from : selection.to)).scrollIntoView())
    return true
  }
  if (!selection.empty) return false
  const node = back ? at.nodeBefore : at.nodeAfter
  if (!node) return false
  if (node.type.name === 'entityRef') {
    view.dispatch(state.tr.setSelection(NodeSelection.create(state.doc, back ? at.pos - node.nodeSize : at.pos)).scrollIntoView())
    return true
  }
  const step = stepOver(node, back)
  view.dispatch(state.tr.setSelection(TextSelection.create(state.doc, at.pos + (back ? -step : step))).scrollIntoView())
  return true
}

// How far one arrow press carries the caret over the node beside it: a character, the two halves
// of a surrogate pair together, an atom whole.
function stepOver(node: ProseMirrorNode, back: boolean): number {
  if (!node.isText) return node.nodeSize
  const text = node.text ?? ''
  if (back && isLowSurrogate(text.charCodeAt(text.length - 1))) return 2
  if (!back && isHighSurrogate(text.charCodeAt(0))) return 2
  return 1
}

// The far edge of a clicked picture or pill, for a selection that grows from it toward `pos`: the
// node stays inside. A text selection keeps its own anchor.
function anchorAwayFrom(selection: Selection, pos: number): number {
  if (!(selection instanceof NodeSelection)) return selection.anchor
  return pos >= selection.from ? selection.from : selection.to
}

// Shift and an arrow on a selected picture or pill grow the selection from it, the node kept
// inside. ProseMirror would drop an inline node's selection to a caret at its edge, and what the
// click chose would fall out of the selection meant to start with it.
function extendFromSelectedRef(view: EditorView, event: KeyboardEvent): boolean {
  if (event.key !== 'ArrowLeft' && event.key !== 'ArrowRight') return false
  if (!event.shiftKey || event.altKey || event.ctrlKey || event.metaKey) return false
  const { state } = view
  const { selection } = state
  if (!(selection instanceof NodeSelection) || selection.node.type.name !== 'entityRef') return false
  const back = event.key === 'ArrowLeft'
  const edge = back ? selection.$from : selection.$to
  const node = back ? edge.nodeBefore : edge.nodeAfter
  let head = edge.pos
  if (node) head += back ? -stepOver(node, back) : stepOver(node, back)
  else head = Selection.findFrom(state.doc.resolve(back ? edge.before() : edge.after()), back ? -1 : 1, true)?.head ?? head
  view.dispatch(state.tr.setSelection(TextSelection.create(state.doc, anchorAwayFrom(selection, head), head)).scrollIntoView())
  return true
}

// Alt+←/→ on a selected picture moves it one place in its gallery — the keyboard's way to what a
// drag does, as Alt+↑/↓ is for a block. Taken whenever a picture is selected, the gallery's end
// included: there the browser would read Alt+← as "back" and leave the page.
function moveSelectedPicture(
  view: EditorView,
  event: KeyboardEvent,
  onAnnounce: ((place: GalleryPlace) => void) | null,
): boolean {
  if (event.key !== 'ArrowLeft' && event.key !== 'ArrowRight') return false
  if (!event.altKey || event.shiftKey || event.ctrlKey || event.metaKey) return false
  const { selection } = view.state
  if (!(selection instanceof NodeSelection) || selection.node.type.name !== 'entityRef') return false
  if (!isImageCode(String(selection.node.attrs.code ?? ''))) return false
  const step = stepPicture(view.state, event.key === 'ArrowLeft' ? -1 : 1)
  if (step) {
    view.dispatch(step.tr.scrollIntoView())
    onAnnounce?.(step.place)
  }
  return true
}

// Shift and a click stretch the selection to the click — a clicked picture whole inside, as Shift
// and an arrow do. Done here where the browser gets it wrong: its own Shift-click lands next to an
// uneditable picture by guesswork, sometimes short of it, and from a selected picture or pill it
// grows from the node's left edge, so a click to the left of it leaves the node out.
function extendByShiftClick(view: EditorView, event: MouseEvent): boolean {
  if (!event.shiftKey || event.button !== 0 || !view.editable) return false
  const { selection } = view.state
  const tile = (event.target as Element | null)?.closest('.md-image')
  const picture = tile && view.dom.contains(tile) ? posOfTile(view, tile) : null
  const fromRef = selection instanceof NodeSelection && selection.node.type.name === 'entityRef'
  if (picture === null && !fromRef) return false
  const pos = picture ?? view.posAtCoords({ left: event.clientX, top: event.clientY })?.pos
  if (pos === undefined) return false
  const anchor = anchorAwayFrom(selection, pos)
  const head = picture !== null && pos >= anchor ? pos + 1 : pos
  event.preventDefault()
  view.focus()
  view.dispatch(view.state.tr.setSelection(TextSelection.create(view.state.doc, anchor, head)))
  return true
}

// Enter on a selected picture opens it — the keyboard's way to what a double click does. Only a
// picture shown as one: a file that is not a picture, or is gone, keeps Enter for the text.
function openSelectedPicture(view: EditorView, event: KeyboardEvent): boolean {
  if (event.key !== 'Enter' || event.shiftKey || event.altKey || event.ctrlKey || event.metaKey) return false
  const { selection } = view.state
  if (!(selection instanceof NodeSelection) || selection.node.type.name !== 'entityRef') return false
  if (!isImageCode(String(selection.node.attrs.code ?? ''))) return false
  const picture = view.nodeDOM(selection.from)
  if (!(picture instanceof HTMLElement) || !picture.classList.contains('md-image--shown')) return false
  picture.dispatchEvent(new CustomEvent(OPEN_PICTURE_EVENT))
  return true
}

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

export const EntityRef = Node.create<EntityRefOptions>({
  name: 'entityRef',
  group: 'inline',
  inline: true,
  atom: true,
  selectable: true,

  addOptions() {
    return { images: false, onAnnounce: null, onDragging: null }
  },

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

  // The plain-text side of a copy: without it an atom copies as nothing, and a code pasted into a
  // chat or a terminal would arrive missing.
  renderText({ node }) {
    return String(node.attrs.code ?? '')
  },

  // Which view draws a node is decided by its code, once: a view handed a node with another code
  // (ProseMirror reuses views while it patches the document) is rebuilt, so a picture never ends up
  // drawing a pill's code or the reverse.
  addNodeView() {
    const update = ({ oldNode, newNode, updateProps }: {
      oldNode: ProseMirrorNode
      newNode: ProseMirrorNode
      updateProps: () => void
    }): boolean => {
      if (newNode.type !== oldNode.type || oldNode.attrs.code !== newNode.attrs.code) return false
      updateProps()
      return true
    }
    const pill = VueNodeViewRenderer(EntityRefView, { update })
    if (!this.options.images) return pill
    const picture = VueNodeViewRenderer(EntityImageView, { update })
    return (props) => (isImageCode(String(props.node.attrs.code ?? '')) ? picture : pill)(props)
  },

  addProseMirrorPlugins() {
    if (!this.options.images) return []
    return [
      new Plugin<DecorationSet>({
        key: PICTURE_LAYOUT,
        state: {
          init: (_config, state) => pictureDecorations(state.doc),
          apply: (tr, previous) =>
            tr.docChanged || tr.getMeta(PICTURE_LAYOUT) ? pictureDecorations(tr.doc) : previous,
        },
        props: {
          decorations: (state) => PICTURE_LAYOUT.getState(state),
          handleKeyDown: (view, event) =>
            openSelectedPicture(view, event) ||
            moveSelectedPicture(view, event, this.options.onAnnounce) ||
            extendFromSelectedRef(view, event) ||
            stepAroundPictures(view, event),
          handleDOMEvents: {
            mousedown: (view, event) => extendByShiftClick(view, event),
          },
        },
        view: (editorView) => {
          // After the node views have rendered: a picture's state class is set by its view.
          const later = (): void => { void nextTick(() => layOutGalleries(editorView)) }
          // A newly measured picture moves the row breaks too, and those are decorations: a
          // transaction that changes nothing in the document rebuilds them.
          const stop = watch(galleryVersion, () => {
            if (editorView.isDestroyed) return
            editorView.dispatch(editorView.state.tr.setMeta(PICTURE_LAYOUT, true).setMeta('addToHistory', false))
          })
          later()
          return { update: later, destroy: stop }
        },
      }),
      pictureDrag({ onDragging: (on) => this.options.onDragging?.(on) }),
    ]
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
  // shared REF_CODE pattern captures the type word. Through the helper `TASK@1a2b3c4d5e`
  // came back as `TASK@1a2b3c4d5e@1a2b3c4d5e`. Replacing the matched range outright has no
  // such convention to collide with.
  //
  // The pill takes the marks the typed character would have had: a code typed inside a bold run
  // stays in it, as the bridge reads and prints it. Inside a link or a code span a code stays text,
  // as the renderer leaves it (Tiptap already skips input rules in code; `null` — not this rule).
  addInputRules() {
    return [
      new InputRule({
        find: TYPED_CODE,
        handler: ({ state, range, match }) => {
          const marks = state.storedMarks ?? state.selection.$from.marks()
          if (marks.some(keepsCodeAsText)) return null
          state.tr.replaceWith(range.from, range.to, this.type.create({ code: canonicalCode(match[0]) }, null, marks))
        },
      }),
    ]
  },

  // Codes arrive pasted far more often than typed — out of a tool result, a chat, another body.
  // Written out rather than with `nodePasteRule`, whose node comes without the marks of the text it
  // replaces: a bold code pasted from a page split its bold run. A code in a link label or a code
  // span stays text, as `markdownToDoc` and the renderer leave it.
  addPasteRules() {
    return [
      new PasteRule({
        find: PASTED_CODE,
        handler: ({ state, range, match }) => {
          // The runner matches a text block and then each of its text nodes again: by then the
          // range of a code already replaced holds something else, and is left alone. Not `null`:
          // that would make the runner drop every replacement of the paste.
          const { doc } = state.tr
          if (canonicalCode(doc.textBetween(range.from, range.to)) !== canonicalCode(match[0])) return
          const marks = doc.nodeAt(range.from)?.marks ?? []
          if (marks.some(keepsCodeAsText)) return
          state.tr.replaceWith(range.from, range.to, this.type.create({ code: canonicalCode(match[0]) }, null, marks))
        },
      }),
    ]
  },
})

function keepsCodeAsText(mark: ProseMirrorMark): boolean {
  return mark.type.name === 'link' || Boolean(mark.type.spec.code)
}
