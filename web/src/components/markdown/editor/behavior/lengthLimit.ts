// A hard length limit: the document cannot grow past what its database column holds.
//
// The limit sits on the STORED markdown, not on the visible text — that is what goes into the
// column, emphasis stars and escaping included. A change that would push it past the limit is
// refused, the way a native `maxlength` refuses the next keystroke: typing simply stops.
//
// Three things pass regardless:
// - a change that does not make an over-long document longer. A body can arrive longer than the
//   limit (written before it existed, or by the agent through another path), and it must stay
//   editable — refusing every edit would forbid even shortening it;
// - undo and redo: they return to a state the document has already been in;
// - content set from outside (`LENGTH_LIMIT_BYPASS`): the value comes from the database, and
//   refusing it would leave the screen showing something other than what is stored.
//
// A paste is not refused but cut to fit, as a native field cuts it: the clipboard text is
// shortened by the overflow and pasted again through the same pipeline, so markdown parsing still
// applies. Serialising may come out a few characters longer than the source (escaping), so the
// cut is retried a few times, each by the remaining overflow.
import { Extension } from '@tiptap/core'
import { Plugin, PluginKey } from '@tiptap/pm/state'
import type { Node as PMNode } from '@tiptap/pm/model'
import type { EditorView } from '@tiptap/pm/view'
import { docToMarkdown } from '../bridge'

export const LENGTH_LIMIT_BYPASS = 'lengthLimitBypass'

const HISTORY_META = 'history$'
const PASTE_RETRIES = 4

export interface LengthLimitOptions {
  /** Limit of the stored markdown; unset — no limit. */
  maxLength: number | undefined
}

export const LengthLimit = Extension.create<LengthLimitOptions>({
  name: 'lengthLimit',

  addOptions() {
    return { maxLength: undefined }
  },

  addProseMirrorPlugins() {
    const max = this.options.maxLength
    if (max === undefined) return []

    // A document is immutable, so its length is measured once: a transaction is checked against
    // both the old and the new document, and the old one was the new one a keystroke ago.
    const lengths = new WeakMap<PMNode, number>()
    function measure(doc: PMNode): number {
      let length = lengths.get(doc)
      if (length === undefined) {
        length = docToMarkdown(doc.toJSON()).length
        lengths.set(doc, length)
      }
      return length
    }

    let view: EditorView | null = null
    // The clipboard text of the paste in flight, and how many cuts it has had.
    let pasted: string | null = null
    let retries = 0

    function pasteCut(text: string) {
      const data = new DataTransfer()
      data.setData('text/plain', text)
      view?.pasteText(text, new ClipboardEvent('paste', { clipboardData: data }))
    }

    return [
      new Plugin({
        key: new PluginKey('lengthLimit'),
        view(editorView) {
          view = editorView
          return { destroy() { view = null } }
        },
        props: {
          handlePaste(_view, event) {
            pasted = event.clipboardData?.getData('text/plain') ?? null
            return false
          },
        },
        filterTransaction(tr, state) {
          if (!tr.docChanged || tr.getMeta(LENGTH_LIMIT_BYPASS) || tr.getMeta(HISTORY_META)) return true
          const next = measure(tr.doc)
          if (next <= max || next <= measure(state.doc)) return true

          const text = pasted
          pasted = null
          if (tr.getMeta('uiEvent') === 'paste' && text && retries < PASTE_RETRIES) {
            const cut = text.length - (next - max)
            if (cut > 0) {
              retries += 1
              queueMicrotask(() => pasteCut(text.slice(0, cut)))
              return false
            }
          }
          retries = 0
          return false
        },
        appendTransaction(transactions) {
          if (transactions.some((tr) => tr.getMeta('uiEvent') === 'paste')) retries = 0
          return null
        },
      }),
    ]
  },
})
