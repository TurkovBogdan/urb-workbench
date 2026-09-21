// Карточка, которая едет за курсором во время переноса блока.
//
// Нативное превью браузер рисует с самого элемента и делает полупрозрачным — управлять ни
// прозрачностью, ни тенью нативного снимка нельзя, это ограничение платформы. Единственный
// способ получить непрозрачную карточку — убрать нативное превью совсем (прозрачным пикселем)
// и вести своё руками.
//
// Превью обязано совпадать с оригиналом один в один: та же ширина, та же разбивка строк, та же
// высота. Иначе текст переверстается в момент захвата, и это читается как «шрифт поехал».
import { ref } from 'vue'
import type { Ref } from 'vue'
import type { Editor } from '@tiptap/core'
import type { EditorView } from '@tiptap/pm/view'

// Создаётся заранее: незагруженную картинку браузер проигнорирует и вернёт снимок по умолчанию.
const EMPTY_DRAG_IMAGE = new Image()
EMPTY_DRAG_IMAGE.src = 'data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7'

interface DraggedBlock { pos: number; dom: HTMLElement }

export interface DragPreview {
  /** Идёт ли перенос — зона подсвечивает себя рамкой, пока он идёт. */
  dragging: Ref<boolean>
  start: (event: DragEvent) => void
  end: () => void
  /** Снять глобальный слушатель и убрать карточку, если размонтировались посреди переноса. */
  dispose: () => void
}

/**
 * @param editor  редактор; до монтирования `undefined`
 * @param handlePos позиция блока под ручкой перетаскивания
 */
export function useDragPreview(
  editor: Ref<Editor | undefined>,
  handlePos: Ref<number | null>,
): DragPreview {
  const dragging = ref(false)
  let ghost: HTMLElement | null = null

  // Блоки, которые уедут. Перетаскивание берёт всё выделение целиком, поэтому и превью обязано
  // показывать всё: карточка с одним абзацем, когда переезжают пять, — прямая ложь о том, что
  // произойдёт при отпускании.
  function draggedBlocks(view: EditorView): DraggedBlock[] {
    const { from, to } = view.state.selection
    const selected: DraggedBlock[] = []
    let handleInSelection = false

    view.state.doc.forEach((node, offset) => {
      if (offset >= to || offset + node.nodeSize <= from) return
      const dom = view.nodeDOM(offset)
      if (dom instanceof HTMLElement) selected.push({ pos: offset, dom })
      if (offset === handlePos.value) handleInSelection = true
    })

    // Выделение берётся, только если оно охватывает несколько блоков И среди них тот, за который
    // тянут. Иначе уедет блок под ручкой, а каретка может стоять совсем в другом месте — и
    // превью показало бы не то, что переезжает.
    if (selected.length > 1 && handleInSelection) return selected

    const pos = handlePos.value
    const handled = pos === null ? null : view.nodeDOM(pos)
    if (pos !== null && handled instanceof HTMLElement) return [{ pos, dom: handled }]
    return selected
  }

  function buildPreview(sources: DraggedBlock[]): HTMLElement {
    // Хост живёт ВНУТРИ зоны правки: снаружи клон потерял бы стили компонента и приехал бы
    // голым текстом.
    const host = document.createElement('div')
    host.className = 'editor__preview'
    host.setAttribute('aria-hidden', 'true')

    const card = document.createElement('div')
    card.className = 'editor__preview-card'

    // Отдельный слой документа: он несёт ту же типографику, что и сам документ (класс `md-body`
    // из общего файла), и получает ТОЧНУЮ ширину оригинала. Ширина здесь — не оформление, а
    // условие совпадения: от неё зависит, где лягут переносы строк, а значит и высота.
    const body = document.createElement('div')
    body.className = 'md-body editor__preview-doc'
    body.style.width = `${sources[0].dom.offsetWidth}px`
    for (const source of sources) body.appendChild(source.dom.cloneNode(true))

    card.appendChild(body)
    host.appendChild(card)
    return host
  }

  // Карточка двигается только трансформом: смещение через `left`/`top` пересчитывало бы
  // раскладку на каждом кадре.
  function moveGhost(x: number, y: number): void {
    if (ghost) ghost.style.transform = `translate3d(${x - 24}px, ${y - 24}px, 0)`
  }

  function trackGhost(event: DragEvent): void {
    moveGhost(event.clientX, event.clientY)
  }

  function start(event: DragEvent): void {
    dragging.value = true

    const view = editor.value?.view
    if (!view || !event.dataTransfer) return
    const sources = draggedBlocks(view)
    if (!sources.length) return

    ghost = buildPreview(sources)
    view.dom.parentElement?.appendChild(ghost)
    moveGhost(event.clientX, event.clientY)

    event.dataTransfer.setDragImage(EMPTY_DRAG_IMAGE, 0, 0)
    // Координаты берём из `dragover`: у события `drag` они в части браузеров нулевые.
    document.addEventListener('dragover', trackGhost)

    editor.value?.commands.markDragSource(sources.map((source) => source.pos))
  }

  // Конец перетаскивания — любой: дроп, отмена по Esc, отпускание мимо цели.
  //
  // prosemirror-dropcursor вешает свои обработчики на сам `editorView.dom`, а источник
  // перетаскивания у нас — ручка, которая лежит рядом с ним, а не внутри. Поэтому `dragend` до
  // плагина не доходит, и после отмены линия вставки остаётся висеть на экране. Пробрасываем
  // событие внутрь: мусор после отмены — отдельный анти-паттерн, индикатор обязан сниматься по
  // тому событию, которое приходит и при неудаче.
  function end(): void {
    dragging.value = false

    document.removeEventListener('dragover', trackGhost)
    ghost?.remove()
    ghost = null

    editor.value?.commands.markDragSource([])
    editor.value?.view.dom.dispatchEvent(new DragEvent('dragend', { bubbles: false }))
  }

  function dispose(): void {
    document.removeEventListener('dragover', trackGhost)
    ghost?.remove()
    ghost = null
  }

  return { dragging, start, end, dispose }
}
