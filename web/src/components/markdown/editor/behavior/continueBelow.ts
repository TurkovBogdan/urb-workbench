// A press in the empty part of the field below the document continues it.
//
// The field is taller than its text (`minHeight`, the bottom padding), and that space is not the
// editable root — ProseMirror never sees a press there. It used to have a stand-in: TrailingNode
// kept an empty paragraph after a closing table, diagram or rule, a line to click into that no key
// could delete. The editor now holds only what markdown stores, so the press itself does the job:
// the caret goes to the end of the text, or — after a block that holds no caret at its end — into
// the gap after it, where typing opens a paragraph.
import type { Editor } from '@tiptap/core'
import type { Node as PMNode } from '@tiptap/pm/model'
import { GapCursor } from '@tiptap/pm/gapcursor'

/** Handle a `mousedown` on the field's body; `true` — the press was taken. */
export function continueBelow(editor: Editor, event: MouseEvent): boolean {
  if (event.button !== 0 || !editor.isEditable) return false
  // Only a press on the body itself, below the document: one inside the text is ProseMirror's.
  if (event.target !== event.currentTarget) return false
  if (event.clientY <= editor.view.dom.getBoundingClientRect().bottom) return false

  // Without it the press would move the focus to the body and blur the editor first.
  event.preventDefault()
  const last = editor.state.doc.lastChild
  if (last && !endsInText(last)) {
    return editor.chain().focus().command(({ tr }) => {
      tr.setSelection(new GapCursor(tr.doc.resolve(tr.doc.content.size))).scrollIntoView()
      return true
    }).run()
  }
  return editor.commands.focus('end')
}

// Whether the caret can stand at the very end of the block: its last textblock is reachable without
// crossing a block that keeps the caret inside (a table's cell) or holds no text at all (a diagram,
// a rule). The gap cursor's own test is internal to prosemirror-gapcursor.
function endsInText(block: PMNode): boolean {
  let node: PMNode | null = block
  while (node) {
    if (node.isTextblock) return true
    if (node.isAtom || node.type.spec.isolating) return false
    node = node.lastChild
  }
  return false
}
