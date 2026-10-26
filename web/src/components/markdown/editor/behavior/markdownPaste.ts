// Pasted markdown is parsed, not dropped in as text.
//
// Without this extension a copied piece of a body was pasted literally: `## Heading` stayed a line
// with hashes, `- item` a paragraph starting with a hyphen. For a markdown editor that is the worst
// possible answer: the person is pasting exactly the format the editor lives on.
//
// Parsing goes through the same markdownToDoc as loading a body, so paste knows everything loading
// knows — including entity codes, which turn into pills right away.
import { Extension } from '@tiptap/core'
import { Plugin, type EditorState } from '@tiptap/pm/state'
import { Fragment, Slice, type Node as PMNode } from '@tiptap/pm/model'
import { markdownToDoc } from '../bridge'
import type { FeatureSet } from '../modes'

const BLANK_LINE = /\n[ \t]*\n/

/**
 * The slice a plain-text paste puts in place of the selection; `null` — nothing to paste.
 *
 * Open edges merge the first and last pasted paragraphs with the text around the caret —
 * otherwise pasting a word mid-line would split the line into three paragraphs. Parsing drops what
 * stood at the edges of the text, so the edges are read before it: a blank line there is a
 * paragraph break (the paste starts or ends a paragraph of its own), any other blank is one space.
 * Without that, `\n\nText` pasted after a code at the end of a paragraph was glued to the code.
 */
export function pastedSlice(state: EditorState, text: string, features: FeatureSet | null): Slice | null {
  const source = text.replace(/\r\n?/g, '\n')
  const parsed = state.schema.nodeFromJSON(markdownToDoc(source, features ?? undefined))
  if (!parsed.content.childCount) return null

  let fragment = parsed.content
  let openStart = fragment.firstChild?.isTextblock ? 1 : 0
  let openEnd = fragment.lastChild?.isTextblock ? 1 : 0
  if (!source.trim()) return new Slice(fragment, openStart, openEnd)

  const { $from, $to } = state.selection
  // What parsing strips — spaces, tabs, line breaks; a no-break space is text and stays.
  const lead = /^[ \t\n]*/.exec(source)?.[0] ?? ''
  const trail = /[ \t\n]*$/.exec(source)?.[0] ?? ''
  // An edge with nothing beyond it in the text block keeps nothing: a break there would only leave
  // an empty paragraph behind, a blank — a space at the edge of a paragraph. A break splits only a
  // paragraph of the document itself (depth 1): in a list item or a table cell it would split the
  // list or the table, so there it is a blank like any other. A blank next to a blank is not added.
  if (lead && $from.parent.isTextblock && $from.parentOffset > 0) {
    if (BLANK_LINE.test(lead) && $from.depth === 1) openStart = 0
    else if (openStart && !blankBeside($from.nodeBefore, 'end')) fragment = withBlank(fragment, 'start')
  }
  if (trail && $to.parent.isTextblock && $to.parentOffset < $to.parent.content.size) {
    if (BLANK_LINE.test(trail) && $to.depth === 1) openEnd = 0
    else if (openEnd && !blankBeside($to.nodeAfter, 'start')) fragment = withBlank(fragment, 'end')
  }

  return new Slice(fragment, openStart, openEnd)
}

/** The neighbour of the caret already separates: a blank at its `side`, or a line break. */
function blankBeside(node: PMNode | null | undefined, side: 'start' | 'end'): boolean {
  if (!node || node.type.name === 'hardBreak') return true
  if (!node.isText) return false
  return side === 'end' ? /\s$/.test(node.text ?? '') : /^\s/.test(node.text ?? '')
}

function withBlank(fragment: Fragment, edge: 'start' | 'end'): Fragment {
  const block = edge === 'start' ? fragment.firstChild : fragment.lastChild
  if (!block?.isTextblock) return fragment
  const blank = block.type.schema.text(' ')
  const content = edge === 'start' ? Fragment.from(blank).append(block.content) : block.content.addToEnd(blank)
  const replaced: PMNode = block.copy(content)
  return edge === 'start'
    ? fragment.replaceChild(0, replaced)
    : fragment.replaceChild(fragment.childCount - 1, replaced)
}

export interface MarkdownPasteOptions {
  /** The field's features; `null` means unrestricted. Paste must know them just as loading does:
   *  the clipboard is exactly how a construct the field's schema does not know gets into it. */
  features: FeatureSet | null
}

export const MarkdownPaste = Extension.create<MarkdownPasteOptions>({
  name: 'markdownPaste',

  addOptions() {
    return { features: null }
  },

  addProseMirrorPlugins() {
    const { features } = this.options
    return [
      new Plugin({
        props: {
          handlePaste(view, event) {
            const text = event.clipboardData?.getData('text/plain')
            // HTML on the clipboard means it was copied from a browser or an editor; the markup
            // is already there, and parsing it as markdown would read the text twice.
            const html = event.clipboardData?.getData('text/html')
            if (!text || html) return false

            // Inside a code block a paste is text and nothing else.
            if (view.state.selection.$from.parent.type.spec.code) return false

            const slice = pastedSlice(view.state, text, features)
            if (!slice) return false

            // Marked the way ProseMirror marks its own paste: the length limit cuts a paste to fit
            // instead of refusing it, and it tells a paste by this mark.
            view.dispatch(
              view.state.tr
                .replaceSelection(slice)
                .scrollIntoView()
                .setMeta('uiEvent', 'paste'),
            )
            return true
          },
        },
      }),
    ]
  },
})
