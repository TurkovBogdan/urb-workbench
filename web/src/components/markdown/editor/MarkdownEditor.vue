<script setup lang="ts">
// Markdown editing zone: Tiptap for the document model, Vuetify for everything visible.
//
// The split is deliberate. Tiptap ships an open core (schema, transactions, drag handle,
// suggestion mechanics) and sells a prebuilt UI kit; taking the core and drawing the chrome
// out of the components already in this application costs a toolbar and a list, and keeps the
// editor inside the project's theme instead of next to a second one.
//
// `v-model` is markdown, not the editor's JSON: the body stays the source of truth and the
// document model is a working representation that exists only while the zone is mounted.
import { onBeforeUnmount, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { EditorContent, useEditor } from '@tiptap/vue-3'
import type { EditorView } from '@tiptap/pm/view'
import StarterKit from '@tiptap/starter-kit'
import { Placeholder } from '@tiptap/extension-placeholder'
import DragHandle from '@tiptap/extension-drag-handle-vue-3'
import { IconGripVertical } from '@tabler/icons-vue'
import { BlockMoves } from './blockMoves'
import { DragSource } from './dragSource'
import { FlatBlocks } from './blocks'
import { EntityRef } from './entityRef'
import { MarkdownPaste } from './markdownPaste'
import { SlashMenuExtension, createSlashItems, useSlashMenu } from './slashMenu'
import SlashMenuPopup from './SlashMenuPopup.vue'
import BubbleToolbar from './BubbleToolbar.vue'
import { markdownToDoc } from './markdownToDoc'
import { docToMarkdown } from './docToMarkdown'

const props = withDefaults(defineProps<{ modelValue: string; minHeight?: string }>(), {
  minHeight: '320px',
})

const emit = defineEmits<{ 'update:modelValue': [value: string] }>()

const { t } = useI18n()

const slash = useSlashMenu()

// Live-region: единственный работающий канал для скринридера — ARIA-атрибуты драга
// (`aria-grabbed`, `aria-dropeffect`) помечены устаревшими ещё в ARIA 1.1, и замены им не
// появилось. Тексты говорят ПОЗИЦИЯМИ, а не индексами: «позиция 3 из 39» человеку понятна,
// «индекс 2» — нет. Режим вежливый, чтобы объявления не перебивали чтение.
const announcement = ref('')

// Блок под ручкой. Команды перемещения работают от выделения, поэтому перед открытием меню
// выделение переносится сюда — заодно это и ответ на вопрос «что я взял».
const handlePos = ref<number | null>(null)
const moveMenu = ref(false)
const moveAt = ref<[number, number]>([0, 0])

// Идёт ли перенос. События перетаскивания всплывают, поэтому хватает трёх обработчиков на
// корне зоны — без подписок на view и без плагинов. Нужно это ради ответа на вопрос «что
// сейчас происходит»: без него единственным признаком переноса остаётся тонкая линия.
const dragging = ref(false)

// Прозрачный пиксель 1×1 вместо нативного снимка. Платформа рисует своё превью с собственной
// прозрачностью, и управлять ею нельзя ни стилями, ни `setDragImage` — единственный способ
// получить непрозрачную карточку это убрать нативное превью совсем и вести своё руками.
// Картинка создаётся заранее: незагруженную браузер проигнорирует и вернёт снимок по умолчанию.
const EMPTY_DRAG_IMAGE = new Image()
EMPTY_DRAG_IMAGE.src = 'data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7'

// Карточка, которая едет за курсором, пока идёт перенос.
let ghost: HTMLElement | null = null

// Счётчик транзакций. Редактор — не реактивный объект, и плавающая панель узнаёт о смене
// каретки только по этому числу: оно же двигает её к новому выделению.
const tick = ref(0)

// The last markdown this component produced. Comparing against it is what keeps the two
// directions from chasing each other: a value coming back unchanged is our own echo.
let mine = props.modelValue
let syncing = false

const editor = useEditor({
  content: markdownToDoc(props.modelValue),
  extensions: [
    StarterKit.configure({
      // Markdown has no underline. Offering the button would let a user create formatting the
      // body cannot store — the editor must not be able to express more than the format.
      underline: false,
      link: { openOnClick: false, autolink: true },
      // Древовидные узлы StarterKit выключены целиком: список, пункт и цитата приходят из
      // blocks.ts плоскими. Держать оба набора нельзя — вставка из буфера собрала бы дерево.
      blockquote: false,
      bulletList: false,
      orderedList: false,
      listItem: false,
      listKeymap: false,
      // Линия вставки: 2 px и цвет выделенной границы — величины из дизайн-фреймворка
      // Atlassian. Она отвечает на вопрос «на какое место встанет», и в единственном
      // контейнере это единственный нужный сигнал: заливку фона добавляют только когда
      // конкурирующих зон несколько.
      // `color: false` — цвет берётся только из класса, а значит из токена темы, и переживает
      // переключение тёмной темы; инлайновый стиль пришлось бы дублировать.
      dropcursor: { width: 2, color: false, class: 'editor__dropcursor' },
    }),
    FlatBlocks,
    BlockMoves.configure({ onAnnounce: (message) => { announcement.value = message } }),
    // Подсказка на пустой строке — там, где стоит каретка (`showOnlyCurrent` по умолчанию),
    // а не только в пустом документе. Текст функцией, а не строкой: так он берётся из словаря
    // при каждой отрисовке и переживёт смену языка, а не застынет на том, что было при
    // создании редактора.
    Placeholder.configure({ placeholder: () => t('common.editor.placeholder') }),
    DragSource,
    EntityRef,
    MarkdownPaste,
    // Список строится функцией: подписи идут из словаря и переживут смену языка.
    SlashMenuExtension.configure({ controller: slash.controller, items: () => createSlashItems(t) }),
  ],
  onUpdate: ({ editor }) => {
    if (syncing) return
    mine = docToMarkdown(editor.getJSON())
    emit('update:modelValue', mine)
  },
  onTransaction: () => { tick.value += 1 },
})

watch(() => props.modelValue, (value) => {
  if (value === mine || !editor.value) return
  syncing = true
  editor.value.commands.setContent(markdownToDoc(value))
  syncing = false
  mine = value
})

onBeforeUnmount(() => {
  document.removeEventListener('dragover', trackGhost)
  ghost?.remove()
  editor.value?.destroy()
})

// Превью под курсором. Нативное браузер рисует с самого элемента и делает полупрозрачным —
// управлять ни прозрачностью, ни тенью нативного снимка нельзя, это ограничение платформы.
// Поэтому подставляем своё изображение: те же блоки на приподнятой карточке.
//
// Превью обязано совпадать с оригиналом один в один — та же ширина, та же разбивка строк, та
// же высота. Иначе текст переверстается в момент захвата, и это читается как «шрифт поехал».

// Блоки, которые уедут. Перетаскивание берёт всё выделение целиком, поэтому и превью обязано
// показывать всё: карточка с одним абзацем, когда переезжают пять, — прямая ложь о том, что
// произойдёт при отпускании.
interface DraggedBlock { pos: number; dom: HTMLElement }

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

  // Отдельный слой документа: он несёт ту же прозаическую типографику, что и `.ProseMirror`,
  // и получает ТОЧНУЮ ширину оригинала. Ширина здесь — не оформление, а условие совпадения:
  // от неё зависит, где лягут переносы строк, а значит и высота.
  const body = document.createElement('div')
  body.className = 'editor__preview-doc'
  body.style.width = `${sources[0].dom.offsetWidth}px`
  for (const source of sources) body.appendChild(source.dom.cloneNode(true))

  card.appendChild(body)
  host.appendChild(card)
  return host
}

function onDragStart(event: DragEvent): void {
  dragging.value = true
  // Слой, привязанный к сущности, на старте переноса положено закрывать.
  moveMenu.value = false

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

// Карточка двигается только трансформом: смещение через `left`/`top` пересчитывало бы
// раскладку на каждом кадре.
function moveGhost(x: number, y: number): void {
  if (ghost) ghost.style.transform = `translate3d(${x - 24}px, ${y - 24}px, 0)`
}

function trackGhost(event: DragEvent): void {
  moveGhost(event.clientX, event.clientY)
}

// Конец перетаскивания — любой: дроп, отмена по Esc, отпускание мимо цели.
//
// prosemirror-dropcursor вешает свои обработчики на сам `editorView.dom`, а источник
// перетаскивания у нас — ручка, которая лежит рядом с ним, а не внутри. Поэтому `dragend` до
// плагина не доходит, и после отмены линия вставки остаётся висеть на экране. Пробрасываем
// событие внутрь: мусор после отмены — отдельный анти-паттерн, индикатор обязан сниматься по
// тому событию, которое приходит и при неудаче.
function endDrag(): void {
  dragging.value = false

  document.removeEventListener('dragover', trackGhost)
  ghost?.remove()
  ghost = null

  editor.value?.commands.markDragSource([])

  editor.value?.view.dom.dispatchEvent(new DragEvent('dragend', { bubbles: false }))
}

function onHandleNode({ pos }: { pos: number }): void {
  handlePos.value = pos
}

// Клик по ручке открывает меню исходов. Это и есть альтернатива по SC 2.5.7: тот же результат
// одним нажатием указателя, без перетаскивания. Отдельной кнопки «…» у блока нет, поэтому
// кнопкой-меню становится сама ручка — двух триггеров на одной сущности быть не должно.
function openMoveMenu(event: Event): void {
  const rect = (event.currentTarget as HTMLElement).getBoundingClientRect()
  moveAt.value = [Math.round(rect.right), Math.round(rect.bottom)]
  if (handlePos.value !== null) editor.value?.commands.setNodeSelection(handlePos.value)
  moveMenu.value = true
}

function move(target: 'up' | 'down' | 'start' | 'end'): void {
  editor.value?.chain().focus().moveBlock(target).run()
  moveMenu.value = false
}

</script>

<template>
  <div
    class="editor"
    :class="{ 'is-dragging': dragging }"
    @dragstart="onDragStart"
    @dragend="endDrag"
    @drop="endDrag"
  >
    <!-- The drag handle is an open extension in Tiptap 3 — it renders nothing by itself, so the
         grip below is ours and follows the block under the pointer. -->
    <DragHandle
      v-if="editor"
      :editor="editor"
      class="editor__grip"
      role="button"
      tabindex="0"
      aria-haspopup="menu"
      aria-label="Переместить блок"
      :aria-expanded="moveMenu"
      :on-node-change="onHandleNode"
      @click="openMoveMenu"
      @keydown.enter.prevent="openMoveMenu"
      @keydown.space.prevent="openMoveMenu"
    >
      <IconGripVertical :size="16" />
    </DragHandle>

    <VMenu v-model="moveMenu" :target="moveAt" location="bottom start">
      <VList density="compact" nav>
        <VListItem @click="move('start')"><VListItemTitle>В начало документа</VListItemTitle></VListItem>
        <VListItem @click="move('up')">
          <VListItemTitle>Переместить вверх</VListItemTitle>
          <template #append><span class="editor__hint">Alt ↑</span></template>
        </VListItem>
        <VListItem @click="move('down')">
          <VListItemTitle>Переместить вниз</VListItemTitle>
          <template #append><span class="editor__hint">Alt ↓</span></template>
        </VListItem>
        <VListItem @click="move('end')"><VListItemTitle>В конец документа</VListItemTitle></VListItem>
      </VList>
    </VMenu>

    <EditorContent :editor="editor" class="editor__body" :style="{ minHeight: props.minHeight }" />

    <SlashMenuPopup :state="slash.state" :controller="slash.controller" />
    <BubbleToolbar :editor="editor" :tick="tick" />

    <div class="editor__live" role="status" aria-live="polite">{{ announcement }}</div>
  </div>
</template>

<style scoped>
.editor {
  background: var(--surface);
  border: 1px solid var(--border-soft);
  border-radius: var(--radius);
  overflow: hidden;
  transition: border-color 160ms ease;
}

/* Пока идёт перенос, зона сама говорит об этом: акцентная рамка с мягким ореолом. Заливка
   фоном тут была бы ошибкой — её берегут для случая, когда зон дропа несколько и надо
   ответить «в какую», а у нас контейнер один. */
.editor.is-dragging {
  border-color: color-mix(in srgb, rgb(var(--v-theme-primary)) 35%, var(--border-soft));
}

/* Ручка — единственная зона захвата, поэтому не меньше 24×24 CSS-пикселей: SC 2.5.8 Target
   Size (AA). Видимая иконка меньше, площадь нажатия добирается размером самой ручки.
   `touch-action: none` — единственный рычаг против скролла страницы: отменять панорамирование
   через preventDefault браузеры больше не дают, и ставить свойство надо на минимальную площадь,
   иначе палец перестанет прокручивать список. */
.editor__grip {
  display: flex;
  align-items: center;
  justify-content: center;
  min-width: 26px;
  min-height: 26px;
  border-radius: 4px;
  color: var(--text-faint);
  cursor: grab;
  opacity: 0.75;
  touch-action: none;
  /* Ручку ставит floating-ui вплотную к блоку — зазор добавляем сдвигом, отступ он бы не учёл. */
  transform: translateX(-4px);
}

/* Видимый focus-ring — часть клавиатурной модели, а не оформление. */
.editor__grip:focus-visible {
  outline: 2px solid rgb(var(--v-theme-primary));
  outline-offset: 2px;
  opacity: 1;
}

.editor__grip:hover {
  background: color-mix(in srgb, rgb(var(--v-theme-on-surface)) 8%, transparent);
  opacity: 1;
}

.editor__grip:active {
  cursor: grabbing;
}

/* `position: relative` здесь не косметика: prosemirror-dropcursor вешает линию вставки в
   `offsetParent` редактора. Без позиционированного предка она уезжала в корень приложения —
   мимо scoped-стилей этого компонента, и рисовалась прозрачной. Отсюда же и containing block:
   линия считает координаты от этого элемента. */
.editor__body {
  /* Отступы названы переменными, потому что от них считается линия вставки: она обязана
     совпадать с текстовой колонкой, а не подбираться к ней вручную. */
  --editor-gutter: 24px;
  --editor-rail: 26px;

  position: relative;
  padding: 16px var(--editor-gutter) 28px;
}

/* ── Что взяли ───────────────────────────────────────────── */

/* Блок, выбранный ручкой перед открытием меню, подсвечивается — это ответ на вопрос «что я
   взял», когда самого переноса ещё нет.
   ВО ВРЕМЯ переноса подсветки нет: блок остаётся ровно таким, каким был. Менять оформление
   источника незачем — что именно уезжает, уже показывает карточка под курсором, а документ
   под ней должен оставаться прежним, чтобы по нему было видно, куда целиться.
   Только блоки верхнего уровня: `ProseMirror-selectednode` навешивается и на выделенный
   атом — пилюлю сущности, — а у неё своя подсветка, и две поверх одной маленькой плашки
   складываются в кашу. */
.editor:not(.is-dragging) .editor__body :deep(.ProseMirror > .ProseMirror-selectednode) {
  background: color-mix(in srgb, rgb(var(--v-theme-primary)) 9%, transparent);
}

/* ── Линия вставки ───────────────────────────────────────── */

/* Линия вставки — ровно линия: тонкая, сплошная, акцентного цвета. Ни свечения, ни теней,
   ни скруглений, ни терминалов. Толщину задаёт опция `width` расширения, цвет — этот класс.
   Позиция едет плавно, чтобы линия переползала между зазорами, а не телепортировалась. */
.editor__body :deep(.editor__dropcursor) {
  background-color: rgb(var(--v-theme-primary));
  border-radius: 0;
  /* Ширину плагин берёт от целевого блока, а блоки у нас разной ширины: у абзацев и
     заголовков стоит мера строки, у блока кода и разделителя — нет. Линия от этого прыгала
     от блока к блоку. Задаём её по текстовой колонке: место вставки — свойство документа,
     а не того блока, рядом с которым оно оказалось.
     Горизонталь считается от `.editor__body`: у absolute это её padding-box, поэтому слева
     складываются отступ зоны и колонка под ручку. */
  left: calc(var(--editor-gutter) + var(--editor-rail)) !important;
  right: var(--editor-gutter) !important;
  width: auto !important;
  max-width: var(--reading-measure, 92ch);
  transition:
    top 120ms ease,
    left 120ms ease,
    width 120ms ease;
}

@media (prefers-reduced-motion: reduce) {
  .editor__body :deep(.editor__dropcursor) { transition-duration: 1ms; }
}

/* ── Исходник на время переноса ──────────────────────────── */

/* Приглушается, но остаётся на месте: видно, откуда вещь взяли и куда она вернётся, если место
   дропа не выбрано. Удалять блок из потока на время переноса нельзя — список схлопнется,
   соседи прыгнут, и точка отсчёта потеряется. Величина 0.4 — из канона.
   Условие на `.is-dragging` страхует от залипшего класса: без переноса приглушать нечего. */
.editor.is-dragging .editor__body :deep(.is-drag-source) {
  opacity: 0.4;
}

.editor__body :deep(.is-drag-source) {
  transition: opacity 120ms ease;
}

@media (prefers-reduced-motion: reduce) {
  .editor__body :deep(.is-drag-source) { transition-duration: 1ms; }
}

/* ── Превью под курсором ─────────────────────────────────── */

/* Карточка едет за курсором сама: нативное превью отключено прозрачным пикселем, потому что
   платформа рисует его со своей прозрачностью. Живёт в дереве зоны правки, поэтому стили
   текста приходят к клону по тем же правилам, что и к самому документу; `fixed` не режется
   `overflow: hidden` у карточки редактора. Позиция — только трансформом. */
.editor__body :deep(.editor__preview) {
  position: fixed;
  top: 0;
  left: 0;
  z-index: 3000;
  opacity: 1;
  /* Поле, в которое попадёт тень: снимок ограничен рамкой элемента, и без запаса тень
     обрезалась бы по краю карточки. Запас считается по радиусу размытия. */
  padding: 26px;
  pointer-events: none;
}

.editor__body :deep(.editor__preview-card) {
  background: var(--surface);
  border: 1px solid var(--border-soft);
  border-radius: var(--radius);
  /* Поле карточки не входит в ширину документа внутри: ширину несёт слой `preview-doc`, и
     менять её отступами нельзя — от неё зависят переносы строк. */
  padding: 14px 18px;
  width: fit-content;
  /* Ни ширину, ни высоту не режем: обрезанная карточка врёт о том, что переезжает. */
  /* Тень задана явно: утилиты elevation Vuetify в эту сборку не попадают, а снимок делается
     с реально отрисованного элемента — класса, которого нет, он бы не увидел. Две тени:
     дальняя даёт высоту, ближняя очерчивает край. */
  box-shadow:
    0 14px 30px -10px rgb(0 0 0 / 0.32),
    0 4px 10px -4px rgb(0 0 0 / 0.18);
}

/* Поля между блоками внутри превью НЕ трогаем: они должны быть ровно теми же, что в
   документе, иначе высота карточки разойдётся с оригиналом. */

/* ── Подтверждение перемещения ───────────────────────────── */

/* Вспышка 700 мс на перемещённом блоке: после перемещения взгляд теряет объект среди соседей,
   и без подтверждения непонятно, встал ли он туда. Только фон — ни размеров, ни раскладки:
   в движении допустимы лишь `transform` и `opacity`, остальное стоит кадров. */
.editor__body :deep(.is-moved) {
  animation: move-flash 700ms cubic-bezier(0.25, 0.1, 0.25, 1);
  border-radius: 4px;
}

@keyframes move-flash {
  from { background-color: color-mix(in srgb, rgb(var(--v-theme-primary)) 20%, transparent); }
  to   { background-color: transparent; }
}

@media (prefers-reduced-motion: reduce) {
  .editor__body :deep(.is-moved) { animation-duration: 1ms; }
  .editor { transition-duration: 1ms; }
}

/* Live-region обязана быть в потоке и не в перерисовываемом поддереве, поэтому её прячут
   отступом, а не `display: none` — скрытое так содержимое скринридер не читает. */
.editor__live {
  position: absolute;
  width: 1px;
  height: 1px;
  margin: -1px;
  padding: 0;
  overflow: hidden;
  clip-path: inset(50%);
  white-space: nowrap;
}

.editor__hint {
  font-family: var(--font-mono);
  font-size: 10px;
  color: var(--text-faint);
  padding-left: 16px;
}

/* ── Документ ─────────────────────────────────────────────
   Правка и просмотр обязаны быть одной типографикой: значения ниже повторяют `.md-body` из
   MarkdownRenderer — те же токены чтения (гарнитура, кегль, насыщенность, мера строки), та же
   шкала заголовков, тот же ритм. Расхождение означало бы, что текст переверстывается в момент
   сохранения, а это ровно то, чего WYSIWYG обязан избегать.
   Повтор, а не общий файл: стили просмотра лежат в scoped-блоке своего компонента, и свести их
   в один источник — отдельная работа. */
.editor__body :deep(.ProseMirror),
.editor__body :deep(.editor__preview-doc) {
  --prose-size: var(--reading-size, 14px);
  /* Один отступ на список и на его уровни — разъехаться им негде. */
  --prose-indent: 1.5em;

  /* Колонка под ручку перетаскивания — ВНУТРИ редактора, а не в отступе обёртки. Ручка встаёт
     левее блока под курсором; лежи эта полоса снаружи `.ProseMirror`, движение мыши к ручке
     выводило бы курсор из зоны, которую слушает плагин, и ручка исчезала бы на подходе —
     схватить её было невозможно. */
  font-family: var(--font-reading);
  font-size: var(--prose-size);
  font-weight: var(--reading-weight, 300);
  line-height: 1.7;
  color: var(--text);
}

/* Эти два — только у настоящего документа: каретке нужен снятый контур, а колонка под ручку
   в превью сдвинула бы текст и сломала совпадение по ширине. */
.editor__body :deep(.ProseMirror) {
  outline: none;
  padding-left: var(--editor-rail);
}

/* main.scss красит голые `p` и `h1`–`h6` для нечитательных экранов, и наследование от
   контейнера эти правила не перебивает — свойства приходится назвать заново. Без этого абзац
   оставался интерфейсным 13px, а пункт списка рядом шёл 14px: разнобой внутри одного текста. */
.editor__body :deep(:is(p, h1, h2, h3, h4, h5, h6)) {
  font-family: inherit;
}

.editor__body :deep(p) {
  font-size: 1em;
  line-height: inherit;
  margin: 0 0 1em;
}

/* Мера строки — выбор человека. Без неё строка в правке тянется на всю ширину зоны и рвётся
   не там, где порвётся в просмотре. */
.editor__body :deep(:is(p, ul, blockquote, h1, h2, h3, h4, h5, h6)) {
  max-width: var(--reading-measure, 92ch);
}

.editor__body :deep(:is(p, li, blockquote)) { text-wrap: pretty; }
.editor__body :deep(:is(h1, h2, h3, h4, h5, h6)) { text-wrap: balance; }

/* Первый блок не добавляет верхнего поля — оно сложилось бы с отступом зоны. То же и в
   превью, плюс снятое нижнее поле у последнего: карточка обязана обнимать содержимое. */
.editor__body :deep(.ProseMirror > :first-child),
.editor__body :deep(.editor__preview-doc > :first-child) { margin-top: 0; }
.editor__body :deep(.editor__preview-doc > :last-child) { margin-bottom: 0; }

/* ── Заголовки ───────────────────────────────────────────── */

.editor__body :deep(:is(h1, h2, h3, h4, h5, h6)) {
  font-family: var(--font-heading, var(--font-reading));
  font-weight: var(--heading-weight, 600);
  color: var(--text);
}

/* Сверху заголовка кратно больше, чем снизу: заголовок принадлежит следующему тексту, и эта
   асимметрия и отделяет раздел от предыдущего. */
.editor__body :deep(h1) { font-size: 1.5em;   line-height: 1.25; margin: 1.6em 0 0.6em;  letter-spacing: -0.018em; }
.editor__body :deep(h2) { font-size: 1.25em;  line-height: 1.3;  margin: 2em 0 0.75em;   letter-spacing: -0.012em; }
.editor__body :deep(h3) { font-size: 1.125em; line-height: 1.35; margin: 1.6em 0 0.5em;  letter-spacing: -0.006em; }
.editor__body :deep(:is(h4, h5, h6)) { font-size: 1em; line-height: 1.4; margin: 1.4em 0 0.4em; }
.editor__body :deep(h5) { color: var(--text-muted); }
.editor__body :deep(h6) {
  font-size: 0.875em;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--text-faint);
}

/* Заголовок сразу за более крупным — это один заголовочный блок, промежуток схлопывается. */
.editor__body :deep(h1 + h2),
.editor__body :deep(h2 + h3),
.editor__body :deep(h3 + h4),
.editor__body :deep(h4 + h5),
.editor__body :deep(h5 + h6) { margin-top: 0.6em; }

/* ── Список ──────────────────────────────────────────────── */

/* Плоский список: <ul> — только рамка, уровень пункта живёт в --depth, а маркер приезжает
   декорацией в data-marker. Браузерная нумерация здесь не работает — пункты разных уровней
   лежат соседями, а не вложенными списками, и <ol> считал бы их подряд. */
.editor__body :deep(ul[data-list]) {
  list-style: none;
  margin: 0.75em 0 1em;
  padding-left: 0;
}

.editor__body :deep(ul[data-list] li) {
  position: relative;
  margin: 0.35em 0;
  line-height: 1.6;
  padding-left: calc((var(--depth, 0) + 1) * var(--prose-indent));
}

/* Маркер — пунктуация, а не содержимое: в полную силу текста колонка точек читалась бы вторым
   столбцом слева. Отступ уровня тот же `--prose-indent`, что у списка целиком. */
.editor__body :deep(ul[data-list] li)::before {
  content: attr(data-marker);
  position: absolute;
  left: calc(var(--depth, 0) * var(--prose-indent));
  width: calc(var(--prose-indent) - 0.45em);
  text-align: right;
  color: var(--text-faint);
  font-variant-numeric: tabular-nums;
}

.editor__body :deep(ul[data-list] li[data-checked])::before {
  content: "☐";
  cursor: pointer;
  color: var(--text-muted);
}

.editor__body :deep(ul[data-list] li[data-checked="true"])::before {
  content: "☑";
  color: rgb(var(--v-theme-primary));
}

.editor__body :deep(ul[data-list] li[data-checked="true"]) {
  color: var(--text-muted);
}

/* ── Цитата ──────────────────────────────────────────────── */

/* Линия — весь сигнал цитаты, поэтому берётся от цвета текста, а не от токена рамки: на
   `--border` она тонет в карточке. Заодно снимается браузерный `margin: 1em 40px`, который
   уводил цитату вправо от прочих блоков и сдвигал ручку перетаскивания. */
.editor__body :deep(blockquote) {
  margin: 1.4em 0;
  border-left: 3px solid color-mix(in srgb, var(--text) 22%, transparent);
  padding: 0.2em 0 0.2em 1em;
  color: var(--text-muted);
}

/* ── Код в строке ────────────────────────────────────────── */

/* Голое правило `code` в main.scss рисует акцентную обводку — для интерфейса это верно, для
   текста нет: в теле таких вставок десятки, и страница превращалась в оранжевую рябь.
   Значения повторяют `.md-codespan` просмотра. */
.editor__body :deep(code) {
  font-family: var(--font-mono);
  /* Моноширинная кажется крупнее пропорциональной при том же кегле — 0.875em это поправка. */
  font-size: 0.875em;
  color: var(--text);
  background: color-mix(in srgb, var(--text) 10%, transparent);
  border: none;
  border-radius: 4px;
  padding: 0.1em 0.35em;
  /* Разорванный переносом спан — два куска; без этого скругление уходит только на внешние края. */
  box-decoration-break: clone;
  -webkit-box-decoration-break: clone;
}

.editor__body :deep(hr) {
  border: none;
  border-top: 1px solid var(--border-soft);
  margin: 1.8em 0;
}

/* Блок кода собран под компонент CodeBlock из просмотра: та же рамка, тот же кегль, та же
   шапка с языком — правка и просмотр не должны выглядеть разными сущностями. */
.editor__body :deep(pre) {
  font-family: var(--font-mono);
  font-size: 12px;
  line-height: 1.6;
  margin: 1.4em 0;
  padding: 0;
  background: none;
  border: 1px solid var(--border-soft);
  border-radius: var(--radius-sm);
  overflow: hidden;
}

/* Шапка с языком — у блока без языка её нет вовсе. */
.editor__body :deep(pre[data-language]:not([data-language=""]))::before {
  content: attr(data-language);
  display: block;
  padding: 6px 10px;
  background: var(--surface);
  border-bottom: 1px solid var(--border-soft);
  color: var(--text-muted);
  font-size: 11px;
  text-transform: lowercase;
  user-select: none;
}

/* Глобальный стиль приложения красит ЛЮБОЙ `code` в акцент и обводит рамкой — внутри `pre`
   это превращало блок в одну огромную оранжевую плашку. Сброс полный, а не только фон. */
.editor__body :deep(pre code) {
  display: block;
  padding: 12px 14px;
  overflow-x: auto;
  color: var(--text);
  background: none;
  border: none;
  border-radius: 0;
  font-size: inherit;
  font-family: inherit;
  white-space: pre;
  tab-size: 2;
}

.editor__body :deep(hr) {
  border: none;
  border-top: 1px solid var(--border-soft);
  margin: 1.4em 0;
}

/* Подсказка — декорация, поэтому оформляется, а не рисуется. `float` с нулевой высотой не
   даёт ей влиять на раскладку: строка остаётся пустой и по высоте, и по положению каретки.
   Только блоки верхнего уровня: в пустом пункте списка подсказка была бы шумом. */
.editor__body :deep(.ProseMirror > .is-empty)::before {
  content: attr(data-placeholder);
  float: left;
  height: 0;
  pointer-events: none;
  color: var(--text-faint);
}
</style>
