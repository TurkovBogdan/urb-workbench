// Цитата — строчный блок, а не контейнер.
//
// В дереве ProseMirror по умолчанию blockquote держит внутри абзацы, и многострочная цитата
// становится ещё одной формой того же содержимого. Здесь многострочная цитата — несколько
// соседних блоков с одним признаком, и каждый по-прежнему ложится в одну строку markdown.
import { InputRule, Node, mergeAttributes } from '@tiptap/core'

export const Quote = Node.create({
  name: 'quote',
  group: 'block',
  content: 'inline*',
  defining: true,

  parseHTML() {
    return [{ tag: 'blockquote' }]
  },

  renderHTML({ HTMLAttributes }) {
    return ['blockquote', mergeAttributes(HTMLAttributes), 0]
  },

  // Сочетание то же, что у выключенного blockquote из StarterKit — но зарегистрировано в ОБОИХ
  // написаниях. При нажатом Shift браузер отдаёт `key: "B"`, и привязка, записанная строчной
  // буквой, не срабатывает никогда: у самого Tiptap это давняя мина, проверено в браузере.
  // С цифрами так не выходит — там выручает запасной разбор по коду клавиши.
  addKeyboardShortcuts() {
    const toQuote = () => this.editor.commands.toggleNode(this.name, 'paragraph')
    return { 'Mod-Shift-b': toQuote, 'Mod-Shift-B': toQuote }
  },

  // Выключив blockquote из StarterKit, мы унесли и его правило ввода: `> ` перестал заводить
  // цитату и оставался литералом, который сериализатор потом экранировал в `\>`.
  addInputRules() {
    return [
      new InputRule({
        find: /^\s*>\s$/,
        handler: ({ chain, range }) => {
          chain().deleteRange(range).setNode(this.name).run()
        },
      }),
    ]
  },
})
