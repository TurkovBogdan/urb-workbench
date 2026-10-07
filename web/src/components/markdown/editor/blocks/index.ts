// Document nodes: the whole flat schema.
//
// `doc` is a sequence of blocks, and a block contains no blocks. By design, not by accident. The
// default ProseMirror tree allows a paragraph inside a list item, an item inside an item, a
// paragraph inside a quote — and every such nesting is yet another shape of the same content that
// the serializer, toolbar commands, drag and the cursor all have to understand.
//
// There is no nesting here at all: a list is one block with a flat row of items (list.ts), a quote
// is a line block (quote.ts), an item holds inline content directly. Hence the key property: one
// block ↔ one DETERMINISTIC piece of markdown, and serialization stops being a guess about how to
// fold a tree.
//
// The only exception is the table (table.ts), and it is declared, not leaked in: its shape is set
// by the format itself — a GFM cell holds only inline content — so its nodes can be walked in
// exactly one way. The serializer gains no choice, so the rule stays intact.
//
// `FlatBlocks` is plugged in INSTEAD OF StarterKit's blockquote / bulletList / orderedList /
// listItem — both sets cannot coexist, a paste from the clipboard would build a tree.
import { Extension } from '@tiptap/core'
import { Quote } from './quote'
import { List, ListItem } from './list'
import { Table, TableBody, TableCell, TableHead, TableRow } from './table'
import { codeLanguages } from './codeLanguage'

export { Quote } from './quote'
export { List, ListItem, type ListKind } from './list'
export {
  Table, TableBody, TableCell, TableHead, TableRow,
  activeColumnAlign, activeTable,
  type ColumnAlign,
} from './table'
export { EntityRef } from './entityRef'

/** Which of our nodes to enable. A disabled node is NOT in the schema — it is not a hidden button. */
export interface FlatBlocksOptions {
  quote: boolean
  list: boolean
  table: boolean
}

export const FlatBlocks = Extension.create<FlatBlocksOptions>({
  name: 'flatBlocks',

  addOptions() {
    return { quote: true, list: true, table: true }
  },

  addExtensions() {
    const nodes = []
    if (this.options.quote) nodes.push(Quote)
    // An item without a list makes no sense, so the two are enabled as a pair.
    if (this.options.list) nodes.push(List, ListItem)
    if (this.options.table) nodes.push(Table, TableHead, TableBody, TableRow, TableCell)
    return nodes
  },

  addProseMirrorPlugins() {
    return [codeLanguages()]
  },
})
