// Вставка markdown разбирается, а не ложится текстом.
//
// Без этого расширения скопированный кусок тела вставлялся буквально: `## Заголовок` оставался
// строкой с решётками, `- пункт` — абзацем с дефисом. Для редактора markdown это худший из
// возможных ответов: человек вставляет ровно тот формат, которым редактор и живёт.
//
// Разбор идёт тем же markdownToDoc, что и загрузка тела, поэтому вставка знает всё, что знает
// загрузка, — включая коды сущностей, которые сразу становятся пилюлями.
import { Extension } from '@tiptap/core'
import { Plugin } from '@tiptap/pm/state'
import { Slice } from '@tiptap/pm/model'
import { markdownToDoc } from './markdownToDoc'

export const MarkdownPaste = Extension.create({
  name: 'markdownPaste',

  addProseMirrorPlugins() {
    return [
      new Plugin({
        props: {
          handlePaste(view, event) {
            const text = event.clipboardData?.getData('text/plain')
            // HTML в буфере — значит копировали из браузера или редактора; там разметка уже
            // есть, и разбирать её как markdown значило бы читать текст дважды.
            const html = event.clipboardData?.getData('text/html')
            if (!text || html) return false

            // В блоке кода вставка — это текст, и ничего кроме.
            if (view.state.selection.$from.parent.type.spec.code) return false

            const parsed = view.state.schema.nodeFromJSON(markdownToDoc(text))
            const fragment = parsed.content
            if (!fragment.childCount) return false

            // Открытые края склеивают первый и последний абзацы вставки с текстом вокруг
            // каретки — иначе вставка слова посреди строки разорвала бы её на три абзаца.
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
