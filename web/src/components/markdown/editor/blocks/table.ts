// Таблица — единственное место, где плоская схема уступает, и уступает осознанно.
//
// Остальные блоки ложатся в одну строку markdown, поэтому сериализатору нечего решать. Таблица
// GFM — минимум три строки и двумерный контейнер, так что буквально это правило на ней не
// держится. Смысл правила, однако, не в счёте строк: оно запрещает АЛЬТЕРНАТИВНЫЕ формы одного
// содержимого, из-за которых печать становится догадкой. У таблицы альтернатив нет:
//
//   - форма фиксирована самим форматом — шапка, разделитель, ряды, и никак иначе;
//   - ячейка по спецификации GFM держит только строчное содержимое: блока внутри не бывает;
//   - значит, обойти узлы можно ровно одним способом, и печать остаётся детерминированной.
//
// Поэтому правило звучит теперь «один блок ↔ один ДЕТЕРМИНИРОВАННЫЙ кусок markdown», а
// произвольная вложенность, ради запрета которой схема и писалась, не возвращается: внутрь
// ячейки блок положить нельзя, и схема это запрещает, а не отговаривает.
//
// Разметка повторяет рендерер дословно — `div.md-table-wrap > table.md-table > thead/tbody`, —
// потому что типографику обе зоны берут из одного файла (`markdown/shared/document.css`).
// Отсюда и отдельные узлы под `thead` и `tbody`: без них полосатость рядов в правке считалась
// бы с шапки и разошлась бы с просмотром на один ряд.
import { Node, mergeAttributes } from '@tiptap/core'
import type { EditorState, Transaction } from '@tiptap/pm/state'
import { Plugin, TextSelection } from '@tiptap/pm/state'
import { Decoration, DecorationSet } from '@tiptap/pm/view'
import type { Node as PMNode } from '@tiptap/pm/model'

/** Выравнивание колонки; `null` — не задано (в markdown это `---` без двоеточий). */
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
      /** Шаг по ячейкам; на последней — новый ряд, как в любом текстовом процессоре. */
      goToCell: (direction: 1 | -1) => ReturnType
    }
  }
}

const ALIGN_CLASS: Record<Exclude<ColumnAlign, null>, string> = {
  left: 'md-align-left',
  center: 'md-align-center',
  right: 'md-align-right',
}

// ── Узлы ──────────────────────────────────────────────────────────────────────

export const TableCell = Node.create({
  name: 'tableCell',
  // Ровно то, что разрешает GFM. Схема запрещает блок внутри ячейки, а не отговаривает от него:
  // иначе таблица стала бы дверью, через которую вложенность вернулась бы в документ.
  content: 'inline*',
  // Каретка не проваливается между ячейками: Backspace в начале ячейки не сливает её с соседней.
  isolating: true,

  addAttributes() {
    return {
      header: {
        default: false,
        parseHTML: (element) => element.tagName === 'TH',
        // В разметку не уезжает: тег и так говорит всё, а дубль пришлось бы синхронизировать.
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
  // Ровно один ряд: в GFM шапка одна, и схема повторяет это ограничение вместо того, чтобы
  // проверять его в сериализаторе.
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
  // Звёздочка, а не плюс: таблица из одной шапки — законный markdown.
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
      // Выравнивание — свойство КОЛОНКИ, а не ячейки: в markdown оно объявлено один раз в
      // строке-разделителе. Держать его на каждой ячейке значило бы синхронизировать копии при
      // любой правке колонки; здесь копия одна, а до ячеек она доезжает декорацией.
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
    // Обёртка со своей прокруткой — та же, что ставит рендерер: тела несут таблицы до дюжины
    // колонок, и без неё широкая таблица растягивала бы страницу.
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

          // Каретка в первую ячейку шапки: таблицу начинают заполнять с заголовков колонок.
          // Ячейку ищем по документу, а не считаем смещением: `replaceSelectionWith` может
          // убрать пустой абзац под кареткой, и арифметика на константах разъехалась бы.
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

        // Из шапки ряд добавляется первым в тело: «после шапки» — это начало тела.
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
        // Шапку удалить нельзя — без неё это уже не таблица GFM. Убрать её целиком можно
        // командой deleteTable, и отказ здесь честнее, чем молчаливое превращение в мусор.
        if (!found || found.isHeader) return false
        if (dispatch) {
          tr.delete(found.rowPos, found.rowPos + found.row.nodeSize)
          // На месте удалённого ряда теперь стоит следующий (или конец тела) — `near` сам найдёт
          // ближайшую позицию, куда каретка вообще может встать.
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
        // Последнюю колонку не удаляем: таблица без колонок не выражается в markdown вовсе.
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
          // Шаг вперёд из последней ячейки заводит новый ряд — так ведёт себя любой текстовый
          // процессор, и таблица заполняется без похода в меню. Назад из первой — некуда.
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
      // В ячейке нет абзацев, поэтому Enter не делит содержимое, а ведёт вниз — к ячейке под
      // текущей, а из последнего ряда заводит новый.
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

// ── Поиск по структуре ────────────────────────────────────────────────────────

interface CellRef {
  table: PMNode
  tablePos: number
  /** Позиция узла `tableBody` — по ней добавляется ряд «после шапки». */
  bodyPos: number
  row: PMNode
  rowPos: number
  cell: PMNode
  cellPos: number
  /** Номер колонки, от нуля. */
  column: number
  isHeader: boolean
}

/** Таблица под кареткой — для хрома, которому нужно к чему привязаться. `null` — каретка вне. */
export function activeTable(state: EditorState): { node: PMNode; pos: number } | null {
  const found = cellAt(state)
  return found ? { node: found.table, pos: found.tablePos } : null
}

/** Выравнивание колонки под кареткой — чтобы панель показывала текущее состояние, а не гадала. */
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

/** Все ряды таблицы подряд — шапка, затем тело — с абсолютной позицией каждого. */
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

/** Позиция каретки в ячейке соседнего ряда той же колонки; `null` — ряда нет. */
function cellBelow(found: CellRef): number | null {
  const rows = rowsOf(found.table, found.tablePos)
  const index = rows.findIndex((entry) => entry.pos === found.rowPos)
  const next = rows[index + 1]
  if (!next) return null
  return cellStart(next, Math.min(found.column, next.row.childCount - 1))
}

/** Позиция каретки в следующей (`1`) или предыдущей (`-1`) ячейке; `null` — край таблицы. */
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

// ── Правка колонок ────────────────────────────────────────────────────────────

// Ряды правятся С КОНЦА: вставка в первый ряд сдвинула бы позиции всех следующих, и собранные
// заранее числа перестали бы указывать туда, куда указывали.
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

// ── Выравнивание на экране ────────────────────────────────────────────────────

// Выравнивание живёт на таблице одним списком, а нужно на каждой ячейке — ровно тот же случай,
// что у номера пункта списка: производное значение приезжает декорацией, а не дублируется в
// атрибутах, которые пришлось бы держать в согласии при каждой правке колонки.
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
