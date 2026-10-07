// The table is the one place where the flat schema gives way, and it does so deliberately.
//
// Every other block maps onto one markdown line, so the serializer has nothing to decide. A GFM
// table is at least three lines and a two-dimensional container, so the rule cannot hold for it
// literally. The point of the rule, though, is not counting lines: it forbids ALTERNATIVE shapes
// of the same content, which turn printing into guesswork. A table has no alternatives:
//
//   - its shape is fixed by the format itself — header, delimiter, rows, and nothing else;
//   - per the GFM spec a cell holds only inline content: there is never a block inside;
//   - so the nodes can be walked in exactly one way, and printing stays deterministic.
//
// Hence the rule now reads "one block ↔ one DETERMINISTIC piece of markdown", while the arbitrary
// nesting the schema was written to forbid does not come back: a block cannot be put inside a
// cell, and the schema forbids it rather than discouraging it.
//
// The markup copies the renderer verbatim — `div.md-table-wrap > table.md-table > thead/tbody` —
// because both zones take their typography from one file (`markdown/shared/document.css`). That
// is also why `thead` and `tbody` have nodes of their own: without them row striping in the
// editor would count from the header and be off by one row from the viewer.
import { Node, mergeAttributes } from '@tiptap/core'
import type { EditorState, Transaction } from '@tiptap/pm/state'
import { Plugin, TextSelection } from '@tiptap/pm/state'
import { Decoration, DecorationSet } from '@tiptap/pm/view'
import type { Node as PMNode } from '@tiptap/pm/model'

/** Column alignment; `null` — unset (in markdown, `---` without colons). */
export type ColumnAlign = 'left' | 'center' | 'right' | null

declare module '@tiptap/core' {
  interface Commands<ReturnType> {
    flatTable: {
      insertTable: (options?: { rows?: number; cols?: number }) => ReturnType
      addRowAfter: () => ReturnType
      deleteRow: () => ReturnType
      addColumnAfter: () => ReturnType
      deleteColumn: () => ReturnType
      setColumnAlign: (align: ColumnAlign) => ReturnType
      deleteTable: () => ReturnType
      /** Step through cells; from the last one, a new row — as in any word processor. */
      goToCell: (direction: 1 | -1) => ReturnType
    }
  }
}

const ALIGN_CLASS: Record<Exclude<ColumnAlign, null>, string> = {
  left: 'md-align-left',
  center: 'md-align-center',
  right: 'md-align-right',
}

// ── Nodes ─────────────────────────────────────────────────────────────────────

export const TableCell = Node.create({
  name: 'tableCell',
  // Exactly what GFM allows. The schema forbids a block inside a cell rather than discouraging it:
  // otherwise the table would become a door through which nesting returns to the document.
  content: 'inline*',
  // The caret does not fall between cells: Backspace at a cell's start does not merge it with
  // the neighbour.
  isolating: true,

  addAttributes() {
    return {
      header: {
        default: false,
        parseHTML: (element) => element.tagName === 'TH',
        // Not rendered into markup: the tag already says it all, and a duplicate would need syncing.
        renderHTML: () => ({}),
      },
    }
  },

  parseHTML() {
    return [{ tag: 'td' }, { tag: 'th' }]
  },

  renderHTML({ HTMLAttributes, node }) {
    return [node.attrs.header ? 'th' : 'td', mergeAttributes(HTMLAttributes), 0]
  },
})

export const TableRow = Node.create({
  name: 'tableRow',
  content: 'tableCell+',

  parseHTML() {
    return [{ tag: 'tr' }]
  },

  renderHTML({ HTMLAttributes }) {
    return ['tr', mergeAttributes(HTMLAttributes), 0]
  },
})

export const TableHead = Node.create({
  name: 'tableHead',
  // Exactly one row: GFM has a single header, and the schema mirrors that constraint instead of
  // checking it in the serializer.
  content: 'tableRow',

  parseHTML() {
    return [{ tag: 'thead' }]
  },

  renderHTML({ HTMLAttributes }) {
    return ['thead', mergeAttributes(HTMLAttributes), 0]
  },
})

export const TableBody = Node.create({
  name: 'tableBody',
  // A star, not a plus: a header-only table is valid markdown.
  content: 'tableRow*',

  parseHTML() {
    return [{ tag: 'tbody' }]
  },

  renderHTML({ HTMLAttributes }) {
    return ['tbody', mergeAttributes(HTMLAttributes), 0]
  },
})

export const Table = Node.create({
  name: 'table',
  group: 'block',
  content: 'tableHead tableBody',
  isolating: true,

  addAttributes() {
    return {
      // Alignment is a property of the COLUMN, not the cell: markdown declares it once in the
      // delimiter row. Keeping it on every cell would mean syncing copies on every column edit;
      // here there is one copy, and it reaches the cells as a decoration.
      align: {
        default: [] as ColumnAlign[],
        parseHTML: (element) => {
          const raw = element.getAttribute('data-align')
          return raw ? (JSON.parse(raw) as ColumnAlign[]) : []
        },
        renderHTML: (attributes) => ({ 'data-align': JSON.stringify(attributes.align ?? []) }),
      },
    }
  },

  parseHTML() {
    return [{ tag: 'table' }]
  },

  renderHTML({ HTMLAttributes }) {
    // A wrapper with its own scrolling — the same one the renderer adds: bodies carry tables of up
    // to a dozen columns, and without it a wide table would stretch the page.
    return [
      'div',
      { class: 'md-table-wrap' },
      ['table', mergeAttributes(HTMLAttributes, { class: 'md-table' }), 0],
    ]
  },

  addCommands() {
    return {
      insertTable: (options) => ({ state, tr, dispatch }) => {
        const rows = Math.max(1, options?.rows ?? 2)
        const cols = Math.max(1, options?.cols ?? 3)
        const { table, tableHead, tableBody, tableRow, tableCell } = state.schema.nodes

        const makeRow = (header: boolean): PMNode => tableRow.create(
          null,
          Array.from({ length: cols }, () => tableCell.create({ header })),
        )

        const node = table.create(
          { align: Array.from({ length: cols }, () => null) },
          [
            tableHead.create(null, makeRow(true)),
            tableBody.create(null, Array.from({ length: rows }, () => makeRow(false))),
          ],
        )

        if (dispatch) {
          const from = tr.selection.from
          tr.replaceSelectionWith(node)

          // Caret into the first header cell: a table is filled in starting from column titles.
          // The cell is searched for in the document rather than computed as an offset:
          // `replaceSelectionWith` may remove the empty paragraph under the caret, and constant
          // arithmetic would drift.
          let target: number | null = null
          tr.doc.nodesBetween(
            Math.max(0, from - 1),
            Math.min(tr.doc.content.size, from + node.nodeSize + 2),
            (child, pos) => {
              if (target === null && child.type.name === 'tableCell') target = pos + 1
            },
          )
          if (target !== null) tr.setSelection(TextSelection.near(tr.doc.resolve(target)))
          tr.scrollIntoView()
        }
        return true
      },

      addRowAfter: () => ({ state, tr, dispatch }) => {
        const found = cellAt(state)
        if (!found) return false
        const { tableRow, tableCell } = state.schema.nodes
        const width = found.row.childCount
        const row = tableRow.create(null, Array.from({ length: width }, () => tableCell.create({ header: false })))

        // From the header, the row goes first in the body: "after the header" is the body's start.
        const at = found.isHeader
          ? found.bodyPos + 1
          : found.rowPos + found.row.nodeSize

        if (dispatch) {
          tr.insert(at, row)
          tr.setSelection(TextSelection.near(tr.doc.resolve(at + 2))).scrollIntoView()
        }
        return true
      },

      deleteRow: () => ({ state, tr, dispatch }) => {
        const found = cellAt(state)
        // The header cannot be deleted — without it this is no longer a GFM table. The whole
        // table can go via deleteTable, and refusing here is more honest than silently turning
        // it into garbage.
        if (!found || found.isHeader) return false
        if (dispatch) {
          tr.delete(found.rowPos, found.rowPos + found.row.nodeSize)
          // The deleted row's place is now taken by the next one (or the body's end) — `near`
          // finds the closest position where the caret can stand at all.
          const at = Math.min(found.rowPos, tr.doc.content.size)
          tr.setSelection(TextSelection.near(tr.doc.resolve(at), -1))
        }
        return true
      },

      addColumnAfter: () => ({ state, tr, dispatch }) => {
        const found = cellAt(state)
        if (!found) return false
        if (dispatch) {
          insertColumn(tr, state, found.tablePos, found.table, found.column + 1)
          setAlign(tr, found.tablePos, found.table, (list) => {
            const next = [...list]
            next.splice(found.column + 1, 0, null)
            return next
          })
        }
        return true
      },

      deleteColumn: () => ({ state, tr, dispatch }) => {
        const found = cellAt(state)
        // The last column is not deleted: a table without columns cannot be expressed in markdown.
        if (!found || found.row.childCount <= 1) return false
        if (dispatch) {
          removeColumn(tr, state, found.tablePos, found.table, found.column)
          setAlign(tr, found.tablePos, found.table, (list) => list.filter((_, i) => i !== found.column))
        }
        return true
      },

      setColumnAlign: (align) => ({ state, tr, dispatch }) => {
        const found = cellAt(state)
        if (!found) return false
        if (dispatch) {
          setAlign(tr, found.tablePos, found.table, (list) => {
            const next = [...list]
            while (next.length < found.row.childCount) next.push(null)
            next[found.column] = align
            return next
          })
        }
        return true
      },

      deleteTable: () => ({ state, tr, dispatch }) => {
        const found = cellAt(state)
        if (!found) return false
        if (dispatch) tr.delete(found.tablePos, found.tablePos + found.table.nodeSize)
        return true
      },

      goToCell: (direction) => ({ state, tr, dispatch }) => {
        const found = cellAt(state)
        if (!found) return false

        const target = neighbourCell(found, direction)
        if (target === null) {
          // Stepping forward from the last cell adds a new row — that is how any word processor
          // behaves, and the table fills in without a trip to the menu. Back from the first:
          // nowhere to go.
          if (direction === -1) return false
          return this.editor.commands.addRowAfter()
        }

        if (dispatch) {
          tr.setSelection(TextSelection.near(tr.doc.resolve(target))).scrollIntoView()
        }
        return true
      },
    }
  },

  addKeyboardShortcuts() {
    return {
      Tab: () => this.editor.commands.goToCell(1),
      'Shift-Tab': () => this.editor.commands.goToCell(-1),
      // A cell has no paragraphs, so Enter does not split the content but moves down — to the
      // cell below, and from the last row it adds a new one.
      Enter: () => {
        const found = cellAt(this.editor.state)
        if (!found) return false
        const below = cellBelow(found)
        if (below === null) return this.editor.commands.addRowAfter()
        return this.editor.commands.command(({ tr, dispatch }) => {
          if (dispatch) tr.setSelection(TextSelection.near(tr.doc.resolve(below))).scrollIntoView()
          return true
        })
      },
    }
  },

  addProseMirrorPlugins() {
    return [columnAlign()]
  },
})

// ── Structure lookup ──────────────────────────────────────────────────────────

interface CellRef {
  table: PMNode
  tablePos: number
  /** Position of the `tableBody` node — a row "after the header" is inserted there. */
  bodyPos: number
  row: PMNode
  rowPos: number
  cell: PMNode
  cellPos: number
  /** Column index, zero-based. */
  column: number
  isHeader: boolean
}

/** The table under the caret — for chrome that needs something to anchor to. `null` — caret outside. */
export function activeTable(state: EditorState): { node: PMNode; pos: number } | null {
  const found = cellAt(state)
  return found ? { node: found.table, pos: found.tablePos } : null
}

/** Alignment of the column under the caret — so the toolbar shows the current state, not a guess. */
export function activeColumnAlign(state: EditorState): ColumnAlign {
  const found = cellAt(state)
  if (!found) return null
  return ((found.table.attrs.align ?? []) as ColumnAlign[])[found.column] ?? null
}

function cellAt(state: EditorState): CellRef | null {
  const { $from } = state.selection
  for (let depth = $from.depth; depth > 0; depth -= 1) {
    if ($from.node(depth).type.name !== 'tableCell') continue

    const cell = $from.node(depth)
    const row = $from.node(depth - 1)
    const section = $from.node(depth - 2)
    const table = $from.node(depth - 3)
    if (!table || table.type.name !== 'table') return null

    const tablePos = $from.before(depth - 3)
    let bodyPos = tablePos + 1
    table.forEach((child, offset) => {
      if (child.type.name === 'tableBody') bodyPos = tablePos + 1 + offset
    })

    return {
      table,
      tablePos,
      bodyPos,
      row,
      rowPos: $from.before(depth - 1),
      cell,
      cellPos: $from.before(depth),
      column: $from.index(depth - 1),
      isHeader: section.type.name === 'tableHead',
    }
  }
  return null
}

/** All table rows in order — header, then body — each with its absolute position. */
function rowsOf(table: PMNode, tablePos: number): { row: PMNode; pos: number }[] {
  const rows: { row: PMNode; pos: number }[] = []
  table.forEach((section, sectionOffset) => {
    const sectionPos = tablePos + 1 + sectionOffset
    section.forEach((row, rowOffset) => {
      rows.push({ row, pos: sectionPos + 1 + rowOffset })
    })
  })
  return rows
}

/** Caret position in the same column's cell of the next row; `null` — no such row. */
function cellBelow(found: CellRef): number | null {
  const rows = rowsOf(found.table, found.tablePos)
  const index = rows.findIndex((entry) => entry.pos === found.rowPos)
  const next = rows[index + 1]
  if (!next) return null
  return cellStart(next, Math.min(found.column, next.row.childCount - 1))
}

/** Caret position in the next (`1`) or previous (`-1`) cell; `null` — the table's edge. */
function neighbourCell(found: CellRef, direction: 1 | -1): number | null {
  const rows = rowsOf(found.table, found.tablePos)
  const rowIndex = rows.findIndex((entry) => entry.pos === found.rowPos)
  if (rowIndex < 0) return null

  const column = found.column + direction
  if (column >= 0 && column < rows[rowIndex].row.childCount) {
    return cellStart(rows[rowIndex], column)
  }

  const neighbour = rows[rowIndex + direction]
  if (!neighbour) return null
  return cellStart(neighbour, direction === 1 ? 0 : neighbour.row.childCount - 1)
}

function cellStart(entry: { row: PMNode; pos: number }, column: number): number {
  let at = entry.pos + 1
  for (let index = 0; index < column; index += 1) at += entry.row.child(index).nodeSize
  return at + 1
}

// ── Column edits ──────────────────────────────────────────────────────────────

// Rows are edited FROM THE END: inserting into the first row would shift the positions of all
// following ones, and numbers collected in advance would stop pointing where they did.
function insertColumn(tr: Transaction, state: EditorState, tablePos: number, table: PMNode, column: number): void {
  const { tableCell } = state.schema.nodes
  const rows = rowsOf(table, tablePos)

  for (let index = rows.length - 1; index >= 0; index -= 1) {
    const entry = rows[index]
    const header = index === 0
    const at = column >= entry.row.childCount
      ? entry.pos + entry.row.nodeSize - 1
      : cellStart(entry, column) - 1
    tr.insert(at, tableCell.create({ header }))
  }
}

function removeColumn(tr: Transaction, state: EditorState, tablePos: number, table: PMNode, column: number): void {
  const rows = rowsOf(table, tablePos)

  for (let index = rows.length - 1; index >= 0; index -= 1) {
    const entry = rows[index]
    if (column >= entry.row.childCount) continue
    const from = cellStart(entry, column) - 1
    tr.delete(from, from + entry.row.child(column).nodeSize)
  }
}

function setAlign(
  tr: Transaction,
  tablePos: number,
  table: PMNode,
  update: (list: ColumnAlign[]) => ColumnAlign[],
): void {
  const current = (table.attrs.align ?? []) as ColumnAlign[]
  tr.setNodeMarkup(tablePos, undefined, { ...table.attrs, align: update(current) })
}

// ── On-screen alignment ───────────────────────────────────────────────────────

// Alignment lives on the table as one list but is needed on every cell — exactly the same case as
// a list item's number: the derived value arrives as a decoration rather than being duplicated in
// attributes that would have to be kept consistent on every column edit.
function columnAlign(): Plugin {
  return new Plugin({
    props: {
      decorations(state) {
        const decorations: Decoration[] = []

        state.doc.descendants((node, pos) => {
          if (node.type.name !== 'table') return true
          const align = (node.attrs.align ?? []) as ColumnAlign[]
          if (!align.some(Boolean)) return false

          for (const entry of rowsOf(node, pos)) {
            entry.row.forEach((cell, offset, index) => {
              const value = align[index]
              if (!value) return
              const from = entry.pos + 1 + offset
              decorations.push(Decoration.node(from, from + cell.nodeSize, { class: ALIGN_CLASS[value] }))
            })
          }
          return false
        })

        return DecorationSet.create(state.doc, decorations)
      },
    },
  })
}
