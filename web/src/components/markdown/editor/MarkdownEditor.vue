<script setup lang="ts">
// Зона правки markdown: Tiptap держит модель документа, Vuetify — всё видимое.
//
// `v-model` — это markdown, а не JSON редактора: источником истины остаётся тело, а модель
// документа существует только пока зона смонтирована. Отсюда и устройство папки — мост
// (`bridge/`) несущая конструкция, а не деталь реализации.
//
// Сам файл занимается ровно сборкой: какие узлы и поведения подключены, что показывает шаблон
// и как выглядит ХРОМ ПРАВКИ. Типографика документа сюда не входит — она общая с просмотром и
// лежит в `markdown/shared/document.css`; элемент ProseMirror получает тот же класс `md-body`,
// что и контейнер рендерера, поэтому оба обслуживаются одним набором правил.
//
// Состав возможностей (`mode` / `features`) — не оформление, а контракт поля: выключенного узла
// в схеме НЕТ, разбор входного markdown к нему приводится, и хром показывает ровно то, что
// сработает. Подробности и наборы — `modes.ts`.
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { EditorContent, useEditor } from '@tiptap/vue-3'
import StarterKit from '@tiptap/starter-kit'
import { Placeholder } from '@tiptap/extension-placeholder'
import DragHandle from '@tiptap/extension-drag-handle-vue-3'
import { IconGripVertical } from '@tabler/icons-vue'
import { EntityRef, FlatBlocks } from './blocks'
import { BlockMoves, DragSource, MarkdownPaste, useDragPreview } from './behavior'
import {
  BubbleToolbar, SlashMenuExtension, SlashMenuPopup, TableControls,
  createSlashItems, useSlashMenu,
} from './controls'
import { docToMarkdown, markdownToDoc } from './bridge'
import { resolveFeatures, type EditorMode, type Feature } from './modes'

const props = withDefaults(defineProps<{
  modelValue: string
  minHeight?: string
  /** Готовый набор возможностей. `simple` — абзац, жирный, курсив и ничего больше. */
  mode?: EditorMode
  /** Точный состав вместо режима; задан — режим не учитывается вовсе. */
  features?: readonly Feature[]
  /** Предел длины ХРАНИМОГО markdown. Не задан — счётчика нет. */
  maxLength?: number
  /**
   * С какой заполненности показывать счётчик, в процентах. `0` — виден всегда, пока поле в
   * фокусе. Превышение показывается независимо от порога и независимо от фокуса: предупреждение,
   * исчезающее при уходе из поля, бесполезно ровно тогда, когда оно нужно.
   */
  limitThreshold?: number
  /**
   * `outlined` — своя рамка и поверхность: зона стоит сама по себе.
   * `plain` — ни рамки, ни фона, ни боковых отступов: поле внутри чужой карточки, и вторая
   * рамка вокруг него читалась бы коробкой в коробке.
   */
  variant?: 'outlined' | 'plain'
  /** Только чтение: документ виден и выделяется, но не меняется. */
  readonly?: boolean
  /** Подсказка на пустой строке. Не задана — общая «Введите / для команд…». */
  placeholder?: string
  /** Имя зоны для вспомогательных технологий: у поля формы оно своё, а не «редактор». */
  ariaLabel?: string
  /**
   * Подпись поля. Стоит НАД зоной, а не плавает в рамке, как у Vuetify: плавающая метка живёт
   * внутри `input`, а здесь внутри — документ, и подпись поверх него перекрывала бы первую строку.
   */
  label?: string
  /** Пояснение под полем: что сюда кладут, если по имени поля это не угадывается. */
  hint?: string
}>(), {
  minHeight: '320px',
  mode: 'full',
  features: undefined,
  maxLength: undefined,
  limitThreshold: 0,
  variant: 'outlined',
  readonly: false,
  placeholder: undefined,
  ariaLabel: undefined,
  label: undefined,
  hint: undefined,
})

// Состав считается один раз: менять возможности на лету значило бы пересобирать схему под
// документом, который в ней уже лежит.
const features = resolveFeatures(props.mode, props.features)
const has = (feature: Feature): boolean => features.has(feature)

// `blur` наружу нужен формам, которые сохраняют по уходу из поля: у Tiptap своего события нет,
// а слушать фокус на контейнере бесполезно — правится вложенный contenteditable.
const emit = defineEmits<{
  'update:modelValue': [value: string]
  blur: []
  focus: []
}>()

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

// Счётчик транзакций. Редактор — не реактивный объект, и плавающая панель узнаёт о смене
// каретки только по этому числу: оно же двигает её к новому выделению.
const tick = ref(0)

// The last markdown this component produced. Comparing against it is what keeps the two
// directions from chasing each other: a value coming back unchanged is our own echo.
let mine = props.modelValue
let syncing = false

// ── Лимит длины ───────────────────────────────────────────────────────────────

// Считаем ХРАНИМЫЙ markdown, а не видимый текст: предел стоит на колонке в базе, и мерить надо
// то, что в неё уедет, — вместе с решётками заголовков, чертами таблицы и экранированием.
const chars = ref(props.modelValue.length)
const focused = ref(false)

const over = computed(() => props.maxLength !== undefined && chars.value > props.maxLength)

const showLimit = computed(() => {
  if (props.maxLength === undefined) return false
  if (over.value) return true
  if (!focused.value) return false
  return chars.value / props.maxLength * 100 >= props.limitThreshold
})

const editor = useEditor({
  content: markdownToDoc(props.modelValue, features),
  // Тот же класс, что у контейнера рендерера: типографика документа приходит из общего файла,
  // и совпадение правки с просмотром становится структурным свойством, а не дисциплиной.
  editorProps: {
    attributes: {
      class: 'md-body',
      // Подпись над полем — обычный текст и с зоной правки ничем не связана; имя для
      // вспомогательных технологий берём из неё же, чтобы не требовать его дважды.
      ...(props.ariaLabel ?? props.label ? { 'aria-label': props.ariaLabel ?? props.label ?? '' } : {}),
    },
  },
  extensions: [
    StarterKit.configure({
      // Markdown has no underline. Offering the button would let a user create formatting the
      // body cannot store — the editor must not be able to express more than the format.
      underline: false,
      // `false` выключает узел или метку СОВСЕМ — её нет в схеме, а не спрятана из панели.
      heading: has('heading') ? undefined : false,
      codeBlock: has('codeBlock') ? undefined : false,
      horizontalRule: has('divider') ? undefined : false,
      bold: has('bold') ? undefined : false,
      italic: has('italic') ? undefined : false,
      strike: has('strike') ? undefined : false,
      // Класс тот же, каким рендерер метит код в строке: одно правило на обе зоны.
      code: has('code') ? { HTMLAttributes: { class: 'md-codespan' } } : false,
      link: has('link') ? { openOnClick: false, autolink: true } : false,
      // Древовидные узлы StarterKit выключены целиком: список, пункт и цитата приходят из
      // blocks/ плоскими. Держать оба набора нельзя — вставка из буфера собрала бы дерево.
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
    FlatBlocks.configure({ quote: has('quote'), list: has('list'), table: has('table') }),
    // Подсказка на пустой строке — там, где стоит каретка (`showOnlyCurrent` по умолчанию),
    // а не только в пустом документе. Текст функцией, а не строкой: так он берётся из словаря
    // при каждой отрисовке и переживёт смену языка, а не застынет на том, что было при
    // создании редактора.
    Placeholder.configure({ placeholder: () => props.placeholder ?? t('common.editor.placeholder') }),
    // Вставка обязана знать состав наравне с загрузкой: через буфер в поле и попадает то,
    // чего его схема не знает.
    MarkdownPaste.configure({ features }),
    // Перемещение блоков идёт в комплекте с ручкой: без блочных конструкций переставлять
    // нечего, а альтернативный путь по SC 2.5.7 нужен ровно там, где есть перетаскивание.
    ...(has('handle')
      ? [
          DragSource,
          BlockMoves.configure({ onAnnounce: (message) => { announcement.value = message } }),
        ]
      : []),
    ...(has('entityRef') ? [EntityRef] : []),
    // Список строится функцией: подписи идут из словаря и переживут смену языка.
    ...(has('slash')
      ? [SlashMenuExtension.configure({
          controller: slash.controller,
          items: () => createSlashItems(t, features),
        })]
      : []),
  ],
  onUpdate: ({ editor }) => {
    if (syncing) return
    mine = docToMarkdown(editor.getJSON())
    chars.value = mine.length
    emit('update:modelValue', mine)
  },
  onTransaction: () => { tick.value += 1 },
  onFocus: () => { focused.value = true; emit('focus') },
  onBlur: () => { focused.value = false; emit('blur') },
  editable: !props.readonly,
})

// Режим чтения приходит извне и может смениться на живом редакторе — например, когда задачу
// удалили, не перезагружая страницу.
watch(() => props.readonly, (value) => editor.value?.setEditable(!value))

const drag = useDragPreview(editor, handlePos)

watch(() => props.modelValue, (value) => {
  if (value === mine || !editor.value) return
  syncing = true
  editor.value.commands.setContent(markdownToDoc(value, features))
  syncing = false
  mine = value
  chars.value = value.length
})

onBeforeUnmount(() => {
  drag.dispose()
  editor.value?.destroy()
})

function onDragStart(event: DragEvent): void {
  // Слой, привязанный к сущности, на старте переноса положено закрывать.
  moveMenu.value = false
  drag.start(event)
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
  <div class="editor-field">
    <span v-if="props.label" class="editor-field__label">{{ props.label }}</span>

    <div
      class="editor"
      :class="[
        `editor--${props.variant}`,
        { 'is-dragging': drag.dragging.value, 'editor--readonly': props.readonly },
      ]"
      @dragstart="onDragStart"
      @dragend="drag.end"
      @drop="drag.end"
    >
      <!-- The drag handle is an open extension in Tiptap 3 — it renders nothing by itself, so
           the grip below is ours and follows the block under the pointer. -->
      <DragHandle
        v-if="editor && has('handle')"
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

      <VMenu v-if="has('handle')" v-model="moveMenu" :target="moveAt" location="bottom start">
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

      <EditorContent
        :editor="editor"
        class="editor__body"
        :style="{
          minHeight: props.minHeight,
          // Колонка под ручку нужна только там, где ручка есть: без блочных конструкций она
          // была бы пустой полосой, отодвигающей текст от края ни за чем.
          '--editor-rail': has('handle') ? '24px' : '0px',
        }"
      />

      <!-- Счётчик лежит в нижней полосе отступа и позиционирован абсолютно: появляясь и исчезая
           по фокусу, он не должен двигать ни одной строки текста. -->
      <div v-if="showLimit" class="editor__limit" :class="{ 'is-over': over }">
        {{ chars }} / {{ props.maxLength }}
      </div>

      <SlashMenuPopup v-if="has('slash')" :state="slash.state" :controller="slash.controller" />
      <BubbleToolbar :editor="editor" :tick="tick" :features="features" />
      <TableControls v-if="has('table')" :editor="editor" :tick="tick" />

      <div v-if="has('handle')" class="editor__live" role="status" aria-live="polite">{{ announcement }}</div>
    </div>

    <span v-if="props.hint" class="editor-field__hint">{{ props.hint }}</span>
  </div>
</template>

<!-- Типографика документа. Тот же файл подключает рендерер — Vite сводит их в один ресурс, и
     копии в сборке не появляется.
     Подключать ОБЯЗАН каждый: без этой строки зона правки получала бы стили только на страницах,
     где рядом оказался рендерер, — и выглядела бы то так, то иначе в зависимости от соседа. -->
<style src="../shared/document.css"></style>

<style scoped>
/* Только хром правки. Как выглядит ТЕКСТ — вопрос документа, а не редактора, и ответ на него
   один на две зоны: `markdown/shared/document.css`. */

/* Обёртка поля: подпись, зона, подсказка. Своей геометрии не несёт — она нужна, только чтобы
   подпись и подсказка стояли в одном потоке с зоной. */
.editor-field {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

/* Подпись над полем, а не плавающая метка Vuetify: там метка лежит внутри `input`, здесь внутри
   документ, и метка поверх него перекрывала бы первую строку. Кегль и цвет — как у подписей
   полей в остальном интерфейсе. */
.editor-field__label {
  font-size: 12px;
  line-height: 1.2;
  color: var(--text-muted);
}

.editor-field__hint {
  font-size: 11px;
  line-height: 1.3;
  color: var(--text-faint);
}

.editor {
  /* Система отсчёта для счётчика длины: он лежит в нижней полосе отступа, а не в потоке. */
  position: relative;
}

.editor--outlined {
  background: var(--surface);
  border: 1px solid var(--border-soft);
  border-radius: var(--radius);
  overflow: hidden;
  transition: border-color 160ms ease;
}

/* Поле внутри чужой карточки: рамку и поверхность даёт она, а боковые отступы — её padding.
   Свои здесь сложились бы с чужими, и текст поля разошёлся бы с заголовком секции над ним. */
.editor--plain .editor__body {
  --editor-gutter: 0px;

  padding: 2px 0 20px;
}

/* Пока идёт перенос, зона сама говорит об этом: акцентная рамка с мягким ореолом. Заливка
   фоном тут была бы ошибкой — её берегут для случая, когда зон дропа несколько и надо
   ответить «в какую», а у нас контейнер один. */
.editor--outlined.is-dragging {
  border-color: color-mix(in srgb, rgb(var(--v-theme-primary)) 35%, var(--border-soft));
}

/* Правка недоступна — курсор об этом говорит. Приглушать текст нельзя: его читают, и удалённая
   задача должна оставаться читаемой. */
.editor--readonly :deep(.ProseMirror) {
  cursor: default;
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
     совпадать с текстовой колонкой, а не подбираться к ней вручную.
     `--editor-rail` приходит из шаблона: без ручки перетаскивания колонка под неё не нужна, и
     текст начинается сразу за отступом зоны. Значение здесь — запасное.
     Сумма этих двух величин НЕ произвольна. Ручку ставит расширение, и ставит её по левому краю
     блока с собственным зазором в 10px; при ширине ручки 26px (минимум 24 по SC 2.5.8 Target
     Size) ей нужно 36px слева от текста. Меньше — и ручка уедет за границу зоны, где её
     подрежет `overflow: hidden`: иконка при этом остаётся видна, а площадь нажатия молча
     теряет несколько пикселей, то есть ломается ровно то, ради чего размер и выбран. */
  --editor-gutter: 14px;
  --editor-rail: 24px;

  position: relative;
  padding: 16px var(--editor-gutter) 28px;
}

/* Каретке нужен снятый контур, а колонка под ручку перетаскивания обязана лежать ВНУТРИ
   `.ProseMirror`: движение мыши к ручке иначе выводило бы курсор из зоны, которую слушает
   плагин, и ручка исчезала бы на подходе — схватить её было невозможно. */
.editor__body :deep(.ProseMirror) {
  outline: none;
  padding-left: var(--editor-rail);
}

/* ── Таблица в правке ────────────────────────────────────── */

/* Пустая ячейка в просмотре не встречается, а в правке это нормальное состояние — только что
   добавленная колонка пуста вся. Без минимума такая ячейка схлопывается в ноль, и попасть в неё
   кареткой нечем. Значение — примерно на слово. */
.editor__body :deep(.md-table :is(th, td)) {
  min-width: 5ch;
}

/* Ячейка под кареткой — чтобы в широкой таблице было видно, где сейчас правишь. Только фон:
   рамка сдвинула бы содержимое соседних ячеек на пиксель. */
.editor__body :deep(.md-table :is(th, td):focus-within) {
  background: color-mix(in srgb, rgb(var(--v-theme-primary)) 7%, transparent);
}

/* Обёртка прокрутки не должна обрезать выделение ячейки по краю таблицы. */
.editor__body :deep(.md-table-wrap) {
  scrollbar-width: thin;
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

/* Клон правимого документа, а не тела просмотра: общий файл снимает `pre-wrap` у всех `md-body`,
   кроме самого ProseMirror, — здесь его надо вернуть. Иначе набранные подряд пробелы схлопнутся,
   строки переверстаются, и высота карточки разойдётся с оригиналом, ради совпадения с которым
   превью и строится. */
.editor__body :deep(.editor__preview-doc) {
  white-space: pre-wrap;
}

/* Поля между блоками внутри превью НЕ трогаем: они должны быть ровно теми же, что в
   документе, иначе высота карточки разойдётся с оригиналом. Первый и последний блок — кроме:
   карточка обязана обнимать содержимое. */
.editor__body :deep(.editor__preview-doc > :last-child) { margin-bottom: 0; }

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

/* ── Лимит длины ─────────────────────────────────────────── */

/* Абсолютно — в нижней полосе отступа зоны: счётчик появляется и исчезает по фокусу, и двигать
   при этом текст он не вправе. Моноширинный, потому что число растёт посимвольно, а
   пропорциональный шрифт заставлял бы строку дёргаться на каждой цифре. */
.editor__limit {
  position: absolute;
  right: 10px;
  bottom: 6px;
  font-family: var(--font-mono);
  font-size: 11px;
  line-height: 1;
  color: var(--text-faint);
  font-variant-numeric: tabular-nums;
  pointer-events: none;
  user-select: none;
}

/* Превышение — не оттенок, а другое состояние: текст сверх предела в базу не поедет, и об этом
   надо сказать тем же цветом, каким приложение говорит об отказе. */
.editor__limit.is-over {
  color: rgb(var(--v-theme-error));
  font-weight: 500;
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
