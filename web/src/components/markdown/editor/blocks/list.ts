// Список — цельный блок с плоским рядом пунктов.
//
// «Вложенность» здесь это число `depth` на пункте: Tab меняет цифру, а не переставляет узлы.
// Отсюда и главное свойство схемы — один пункт ложится в одну строку markdown, и сериализатору
// нечего сворачивать. Ценой становится всё, что браузер делал бы сам: нумерация, маркеры и
// отступы считаются здесь, потому что пункты разных уровней лежат соседями, а не вложенными
// списками, и `ol` считал бы их подряд.
import { InputRule, Node, mergeAttributes } from '@tiptap/core'
import type { ChainedCommands, Editor } from '@tiptap/core'
import type { EditorState } from '@tiptap/pm/state'
import { Plugin, PluginKey, TextSelection } from '@tiptap/pm/state'
import { Decoration, DecorationSet } from '@tiptap/pm/view'
import type { Node as PMNode } from '@tiptap/pm/model'

// Форма того, что Tiptap передаёт в обработчик правила ввода; полного типа наружу он не отдаёт.
interface InputRuleProps {
  state: EditorState
  range: { from: number; to: number }
  match: RegExpMatchArray
  chain: () => ChainedCommands
}

export interface ListKind {
  ordered: boolean
  /** `null` — обычный пункт; `true`/`false` — пункт-галочка и её состояние. */
  checked: boolean | null
}

declare module '@tiptap/core' {
  interface Commands<ReturnType> {
    flatBlocks: {
      /** Имя с префиксом: `toggleList` уже занят типами @tiptap/extension-list, и
       *  объявление поверх него склеивается в union вместо замены. */
      toggleFlatList: (kind: ListKind) => ReturnType
      indentListItem: () => ReturnType
      outdentListItem: () => ReturnType
    }
  }
}

// ── Пункт ─────────────────────────────────────────────────────────────────────

export const ListItem = Node.create({
  name: 'listItem',
  content: 'inline*',
  defining: true,

  addAttributes() {
    return {
      depth: {
        default: 0,
        parseHTML: (element) => Number(element.getAttribute('data-depth') ?? 0),
        // `--depth` уезжает в CSS как отступ: уровень это оформление пункта, а не его место
        // в структуре.
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
        // Класс тот же, каким рендерер метит пункт-галочку: типографику документа обе зоны
        // берут из одного файла (`markdown/shared/document.css`), и совпадать они должны
        // разметкой, а не двумя похожими наборами правил.
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

// ── Список ────────────────────────────────────────────────────────────────────

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
            // Тот же вид — выключаем список: каждый пункт становится абзацем, уровни теряются
            // вместе со списком, потому что в абзаце их негде хранить.
            const blocks: PMNode[] = []
            top.node.forEach((item) => blocks.push(paragraph.create(null, item.content)))
            if (dispatch) tr.replaceWith(top.pos, top.pos + top.node.nodeSize, blocks)
            return true
          }

          // Другой вид — переписываем атрибуты пунктов, не трогая содержимое.
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

  // Правила ввода markdown. Ушли вместе с выключенными узлами StarterKit, а без них редактор
  // markdown перестаёт понимать markdown: набранный `- ` оставался текстом.
  addInputRules() {
    const toList = (kind: ListKind) => ({ state, chain, range }: InputRuleProps): void => {
      // Внутри пункта `- ` — это просто дефис. Без проверки правило поймало бы начало пункта и
      // командой того же вида РАСПУСТИЛО бы список.
      if (itemAt(state)) return
      chain().deleteRange(range).toggleFlatList(kind).run()
    }

    return [
      new InputRule({ find: /^\s*[-+*]\s$/, handler: toList({ ordered: false, checked: null }) }),
      new InputRule({ find: /^\s*\d+[.)]\s$/, handler: toList({ ordered: true, checked: null }) }),
      // `- [ ] ` одним махом не набрать: `- ` срабатывает раньше. Поэтому галочка ставится уже
      // внутри пункта — ровно так же, как это делается в Notion.
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

      // Те же сочетания, что у выключенных узлов StarterKit: человек, знающий любой другой
      // редактор на Tiptap, приходит сюда с готовой мышечной памятью.
      'Mod-Shift-8': () => this.editor.commands.toggleFlatList({ ordered: false, checked: null }),
      'Mod-Shift-7': () => this.editor.commands.toggleFlatList({ ordered: true, checked: null }),
      'Mod-Shift-9': () => this.editor.commands.toggleFlatList({ ordered: false, checked: false }),
    }
  },

  addProseMirrorPlugins() {
    return [listMarkers(), taskToggle()]
  },
})

// ── Позиционирование ──────────────────────────────────────────────────────────

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

// ── Уровень пункта ────────────────────────────────────────────────────────────

type Dispatch = ((args?: unknown) => void) | undefined

// Уровень не может обогнать предыдущий пункт больше чем на единицу — иначе появился бы
// «вложенный» пункт без родителя, а список перестал бы отображаться как список.
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
    // Пункты, которые лежали глубже, едут следом — иначе они отвязались бы от своего пункта.
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

// ── Выход из списка ───────────────────────────────────────────────────────────

// Enter в пустом последнем пункте закрывает список — единственный способ выйти из него, не
// прибегая к мыши.
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

// Backspace в начале пункта: сперва поднимает уровень, и только у самого первого пункта
// нулевого уровня распускает список. Так удаление не проваливает текст в соседний блок.
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

// ── Маркеры ───────────────────────────────────────────────────────────────────

const MARKERS = new PluginKey('flatListMarkers')

// Номер пункта — производное от плоского ряда, а не хранимое значение: держать его в атрибуте
// значило бы перенумеровывать половину документа на каждый Enter. CSS сам посчитать не может
// (уровни лежат в одном ряду, а не вложенными списками), поэтому номер приезжает декорацией.
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

// ── Галочка ───────────────────────────────────────────────────────────────────

// Клик по псевдоэлементу приходит на сам <li>, так что галочку от текста отличает только
// координата: граница — левый отступ пункта, за которым начинается содержимое. Берётся из
// вычисленных стилей, а не константой, иначе уровень вложенности сдвинул бы её.
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
