// Slash menu: the Notion gesture, assembled from the open half of Tiptap.
//
// `@tiptap/suggestion` (MIT) provides only the mechanics — trigger character, query, range,
// key interception. It renders nothing, which is the reason to use it: the menu below is an
// ordinary Vuetify list, so it inherits the application's theme instead of importing another
// design system to get a popup. Tiptap's own prebuilt menu is the part that is paid for.
import { Extension } from '@tiptap/core'
import type { Editor, Range } from '@tiptap/core'
import { shallowRef, reactive } from 'vue'
import Suggestion from '@tiptap/suggestion'
import type { SuggestionProps } from '@tiptap/suggestion'

import type { Component } from 'vue'
import {
  IconAlignLeft, IconH1, IconH2, IconH3, IconList, IconListNumbers, IconListCheck,
  IconBlockquote, IconSourceCode, IconSeparatorHorizontal,
} from '@tabler/icons-vue'

export interface SlashItem {
  id: string
  title: string
  icon: Component
  /** Привязка в записи Tiptap, например `Mod-Shift-8`. `null` — сочетания нет.
   *  Подписи для меню выводятся из неё же: два независимых поля разъехались бы. */
  keys: string | null
  /** Латинские и русские триггеры: в меню набирают, и попасть должны оба написания. */
  keywords: string[]
  /** Номер группы. Группы разделяются чертой — чтобы типы блоков читались отдельно. */
  group: number
  run: (editor: Editor, range: Range) => void
}

// Каждая команда разбивает `/запрос` первой: диапазон покрывает и сам слэш, и оставить его —
// классическая ошибка такого меню.
function at(editor: Editor, range: Range) {
  return editor.chain().focus().deleteRange(range)
}

// На маке модификатор рисуется символом, в остальных местах словом. Сочетания при этом одни и
// те же: Tiptap сам разбирает `Mod` как Cmd или Ctrl.
const IS_MAC = typeof navigator !== 'undefined' && /Mac|iPhone|iPad/.test(navigator.platform || navigator.userAgent)

/** Подписи клавиш для меню — выводятся из самой привязки, поэтому разойтись с ней не могут. */
export function shortcutLabels(keys: string | null): string[] {
  if (!keys) return []
  return keys.split('-').map((part) => {
    if (part === 'Mod') return IS_MAC ? '⌘' : 'Ctrl'
    if (part === 'Shift') return '⇧'
    if (part === 'Alt') return IS_MAC ? '⌥' : 'Alt'
    return part.length === 1 ? part.toUpperCase() : part
  })
}

// Буквенная клавиша с Shift приходит от браузера заглавной, и привязка, записанная строчной,
// не срабатывает никогда. Поэтому регистрируем оба написания — та же мина, что была у цитаты.
function bindings(keys: string): string[] {
  const tail = keys.slice(keys.lastIndexOf('-') + 1)
  if (tail.length !== 1 || !/[a-z]/i.test(tail)) return [keys]
  const head = keys.slice(0, keys.lastIndexOf('-') + 1)
  return [head + tail.toLowerCase(), head + tail.toUpperCase()]
}

/**
 * Пункты меню. Подписи сочетаний соответствуют РЕАЛЬНО работающим клавишам: заголовки, абзац и
 * блок кода держит StarterKit, списки и цитату — наши плоские узлы (blocks.ts), и сочетания там
 * выбраны те же, что у выключенных узлов StarterKit.
 */
export function createSlashItems(t: (key: string) => string): SlashItem[] {
  return [
    {
      id: 'paragraph', group: 1, icon: IconAlignLeft,
      title: t('common.editor.slash.paragraph'), keys: 'Mod-Alt-0',
      keywords: ['text', 'p', 'текст', 'абзац'],
      run: (editor, range) => at(editor, range).setParagraph().run(),
    },
    {
      id: 'h1', group: 2, icon: IconH1,
      title: t('common.editor.slash.h1'), keys: 'Mod-Alt-1',
      keywords: ['h1', 'heading', 'заголовок'],
      run: (editor, range) => at(editor, range).toggleHeading({ level: 1 }).run(),
    },
    {
      id: 'h2', group: 2, icon: IconH2,
      title: t('common.editor.slash.h2'), keys: 'Mod-Alt-2',
      keywords: ['h2', 'heading', 'заголовок'],
      run: (editor, range) => at(editor, range).toggleHeading({ level: 2 }).run(),
    },
    {
      id: 'h3', group: 2, icon: IconH3,
      title: t('common.editor.slash.h3'), keys: 'Mod-Alt-3',
      keywords: ['h3', 'heading', 'заголовок'],
      run: (editor, range) => at(editor, range).toggleHeading({ level: 3 }).run(),
    },
    {
      id: 'bulletList', group: 3, icon: IconList,
      title: t('common.editor.slash.bulletList'), keys: 'Mod-Shift-8',
      keywords: ['list', 'bullet', 'список', 'маркированный'],
      run: (editor, range) => at(editor, range).toggleFlatList({ ordered: false, checked: null }).run(),
    },
    {
      id: 'orderedList', group: 3, icon: IconListNumbers,
      title: t('common.editor.slash.orderedList'), keys: 'Mod-Shift-7',
      keywords: ['ordered', 'number', 'нумерованный'],
      run: (editor, range) => at(editor, range).toggleFlatList({ ordered: true, checked: null }).run(),
    },
    {
      id: 'taskList', group: 3, icon: IconListCheck,
      title: t('common.editor.slash.taskList'), keys: 'Mod-Shift-9',
      keywords: ['task', 'todo', 'check', 'чек', 'задача'],
      run: (editor, range) => at(editor, range).toggleFlatList({ ordered: false, checked: false }).run(),
    },
    {
      id: 'quote', group: 4, icon: IconBlockquote,
      title: t('common.editor.slash.quote'), keys: 'Mod-Shift-b',
      keywords: ['quote', 'цитата', 'врезка'],
      run: (editor, range) => at(editor, range).toggleNode('quote', 'paragraph').run(),
    },
    {
      id: 'codeBlock', group: 4, icon: IconSourceCode,
      title: t('common.editor.slash.codeBlock'), keys: 'Mod-Alt-c',
      keywords: ['code', 'код', 'fence'],
      run: (editor, range) => at(editor, range).toggleCodeBlock().run(),
    },
    {
      id: 'divider', group: 4, icon: IconSeparatorHorizontal,
      title: t('common.editor.slash.divider'), keys: null,
      keywords: ['hr', 'divider', 'разделитель'],
      run: (editor, range) => at(editor, range).setHorizontalRule().run(),
    },
  ]
}

function matches(item: SlashItem, query: string): boolean {
  const needle = query.trim().toLowerCase()
  if (!needle) return true
  return item.title.toLowerCase().includes(needle)
    || item.keywords.some((keyword) => keyword.startsWith(needle))
}

// What the popup component renders. Kept as one reactive object so the extension (created
// before the popup mounts) and the component (mounted later) never have to find each other.
export interface SlashState {
  open: boolean
  items: SlashItem[]
  active: number
  left: number
  top: number
  bottom: number
}

export interface SlashMenu {
  state: SlashState
  controller: SlashController
}

export interface SlashController {
  /** Диапазон набранного `/запроса`, пока меню открыто. `null` — меню закрыто. */
  activeRange: () => Range | null
  start: (props: SuggestionProps<SlashItem, SlashItem>) => void
  update: (props: SuggestionProps<SlashItem, SlashItem>) => void
  exit: () => void
  key: (event: KeyboardEvent) => boolean
  pick: (index: number) => void
}

export function useSlashMenu(): SlashMenu {
  const state = reactive<SlashState>({ open: false, items: [], active: 0, left: 0, top: 0, bottom: 0 })
  // The command closes over the current suggestion range, so it is replaced on every update
  // rather than rebuilt from state — a stale range would apply the item to the wrong place.
  const apply = shallowRef<((item: SlashItem) => void) | null>(null)
  // Диапазон нужен не только для выбора мышью: по нему же сочетание клавиш убирает набранный
  // `/запрос`, иначе команда применится, а слэш останется в тексте.
  const range = shallowRef<Range | null>(null)

  const place = (props: SuggestionProps<SlashItem, SlashItem>): void => {
    const rect = props.clientRect?.()
    state.items = props.items
    state.active = 0
    apply.value = props.command
    range.value = props.range
    if (!rect) return
    state.left = rect.left
    state.top = rect.bottom
    state.bottom = rect.top
  }

  const pick = (index: number): void => {
    const item = state.items[index]
    if (item) apply.value?.(item)
  }

  return {
    state,
    controller: {
      activeRange: () => (state.open ? range.value : null),
      start: (props) => { place(props); state.open = true },
      update: (props) => place(props),
      exit: () => { state.open = false; apply.value = null; range.value = null },
      pick,
      key: (event) => {
        if (!state.open || !state.items.length) return false
        if (event.key === 'ArrowDown') {
          state.active = (state.active + 1) % state.items.length
          return true
        }
        if (event.key === 'ArrowUp') {
          state.active = (state.active - 1 + state.items.length) % state.items.length
          return true
        }
        if (event.key === 'Enter' || event.key === 'Tab') {
          pick(state.active)
          return true
        }
        if (event.key === 'Escape') {
          state.open = false
          return true
        }
        return false
      },
    },
  }
}

export const SlashMenuExtension = Extension.create<{
  controller: SlashController | null
  items: (() => SlashItem[]) | null
}>({
  name: 'slashMenu',

  // Выше остальных: пока меню открыто, сочетание обязано пройти через нас — иначе команда
  // сработает раньше, и убирать `/запрос` будет уже нечем.
  priority: 1000,

  addOptions() {
    return { controller: null, items: null }
  },

  // Те же сочетания, что подписаны в меню, но с одной добавкой: открытое меню они сперва
  // закрывают, удаляя набранный `/запрос`. Закрытое меню их не касается — обработчик
  // возвращает false, и дальше работает обычная привязка из blocks.ts или StarterKit.
  addKeyboardShortcuts() {
    const { controller, items } = this.options
    const shortcuts: Record<string, () => boolean> = {}

    for (const item of items?.() ?? []) {
      if (!item.keys) continue
      const run = (): boolean => {
        const range = controller?.activeRange()
        if (!range) return false
        item.run(this.editor, range)
        return true
      }
      for (const binding of bindings(item.keys)) shortcuts[binding] = run
    }

    return shortcuts
  },

  addProseMirrorPlugins() {
    const { controller, items } = this.options
    return [
      Suggestion<SlashItem, SlashItem>({
        editor: this.editor,
        char: '/',
        // A slash inside a word is a slash — a path, a date, a fraction. Only one that opens a
        // token starts the menu.
        allowSpaces: false,
        // В блоке кода слэш — это слэш: путь, регулярка, комментарий. Меню там не просто лишнее,
        // оно опасно — любая его команда сменила бы тип блока и разнесла код.
        allow: ({ editor }) => !editor.isActive('codeBlock'),
        items: ({ query }) => (items?.() ?? []).filter((item) => matches(item, query)),
        command: ({ editor, range, props }) => props.run(editor, range),
        render: () => ({
          onStart: (props) => controller?.start(props),
          onUpdate: (props) => controller?.update(props),
          onExit: () => controller?.exit(),
          onKeyDown: ({ event }) => controller?.key(event) ?? false,
        }),
      }),
    ]
  },
})
