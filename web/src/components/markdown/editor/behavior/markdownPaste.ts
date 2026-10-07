// Pasted markdown is parsed, not dropped in as text.
//
// Without this extension a copied piece of a body was pasted literally: `## Heading` stayed a line
// with hashes, `- item` a paragraph starting with a hyphen. For a markdown editor that is the worst
// possible answer: the person is pasting exactly the format the editor lives on.
//
// Parsing goes through the same markdownToDoc as loading a body, so paste knows everything loading
// knows — including entity codes, which turn into pills right away.
import { Extension } from '@tiptap/core'
import { Plugin } from '@tiptap/pm/state'
import { Slice } from '@tiptap/pm/model'
import { markdownToDoc } from '../bridge'
import type { FeatureSet } from '../modes'

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

            const parsed = view.state.schema.nodeFromJSON(markdownToDoc(text, features ?? undefined))
            const fragment = parsed.content
            if (!fragment.childCount) return false

            // Open edges merge the first and last pasted paragraphs with the text around the
            // caret — otherwise pasting a word mid-line would split the line into three paragraphs.
            const openStart = fragment.firstChild?.isTextblock ? 1 : 0
            const openEnd = fragment.lastChild?.isTextblock ? 1 : 0

            view.dispatch(view.state.tr.replaceSelection(new Slice(fragment, openStart, openEnd)).scrollIntoView())
            return true
          },
        },
      }),
    ]
  },
})
