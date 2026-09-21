// Узлы документа: плоская схема целиком.
//
// `doc` — последовательность блоков, блок не содержит блоков. Так задумано, а не так вышло.
// Дерево ProseMirror по умолчанию разрешает абзац внутри пункта списка, пункт внутри пункта,
// абзац внутри цитаты — и каждая такая вложенность это ещё одна форма одного и того же
// содержимого, которую обязаны понимать сериализатор, команды тулбара, перетаскивание и курсор.
//
// Здесь вложенности нет ни одной: список — цельный блок с плоским рядом пунктов (list.ts),
// цитата — строчный блок (quote.ts), пункт хранит строчное содержимое напрямую. Отсюда главное
// свойство: один блок ↔ один ДЕТЕРМИНИРОВАННЫЙ кусок markdown, и сериализация перестаёт быть
// догадкой о том, как свернуть дерево.
//
// Единственное исключение — таблица (table.ts), и оно объявлено, а не просочилось: её форму
// задаёт сам формат, ячейка по GFM держит только строчное содержимое, поэтому обойти её узлы
// можно ровно одним способом. Выбор у сериализатора не появляется, а значит и правило цело.
//
// `FlatBlocks` подключается ВМЕСТО blockquote / bulletList / orderedList / listItem из
// StarterKit — держать оба набора нельзя, вставка из буфера собрала бы дерево.
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

/** Какие из наших узлов поднимать. Выключенного узла в схеме НЕТ — это не спрятанная кнопка. */
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
    // Пункт без списка бессмыслен, поэтому они включаются парой.
    if (this.options.list) nodes.push(List, ListItem)
    if (this.options.table) nodes.push(Table, TableHead, TableBody, TableRow, TableCell)
    return nodes
  },

  addProseMirrorPlugins() {
    return [codeLanguages()]
  },
})
