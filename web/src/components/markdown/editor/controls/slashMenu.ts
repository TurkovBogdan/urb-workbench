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
import type { BlockFeature, FeatureSet } from '../modes'
import {
  IconAlignLeft, IconH1, IconH2, IconH3, IconList, IconListNumbers, IconListCheck,
  IconBlockquote, IconSourceCode, IconSchema, IconSeparatorHorizontal, IconTable,
} from '@tabler/icons-vue'

export interface SlashItem {
  id: string
  title: string
  icon: Component
  /** The feature without which the item is not shown. `null` — always present (paragraph). */
  feature: BlockFeature | null
  /** The binding in Tiptap notation, e.g. `Mod-Shift-8`. `null` — no shortcut.
   *  The menu labels are derived from it too: two independent fields would drift apart. */
  keys: string | null
  /** Latin and Russian triggers: people type into the menu, and both spellings must match. */
  keywords: string[]
  /** Group number. Groups are separated by a rule so block types read as separate sets. */
  group: number
  run: (editor: Editor, range: Range) => void
}

// Every command deletes the `/query` first: the range covers the slash itself too, and leaving it
// behind is the classic bug of such a menu.
function at(editor: Editor, range: Range) {
  return editor.chain().focus().deleteRange(range)
}

// On a Mac the modifier is drawn as a symbol, elsewhere as a word. The shortcuts themselves are
// the same: Tiptap resolves `Mod` to Cmd or Ctrl on its own.
const IS_MAC = typeof navigator !== 'undefined' && /Mac|iPhone|iPad/.test(navigator.platform || navigator.userAgent)

/** Key labels for the menu — derived from the binding itself, so they cannot drift from it. */
export function shortcutLabels(keys: string | null): string[] {
  if (!keys) return []
  return keys.split('-').map((part) => {
    if (part === 'Mod') return IS_MAC ? '⌘' : 'Ctrl'
    if (part === 'Shift') return '⇧'
    if (part === 'Alt') return IS_MAC ? '⌥' : 'Alt'
    return part.length === 1 ? part.toUpperCase() : part
  })
}

// A letter key with Shift arrives from the browser in uppercase, and a binding written in
// lowercase never fires. So both cases are registered — the same trap the quote had.
function bindings(keys: string): string[] {
  const tail = keys.slice(keys.lastIndexOf('-') + 1)
  if (tail.length !== 1 || !/[a-z]/i.test(tail)) return [keys]
  const head = keys.slice(0, keys.lastIndexOf('-') + 1)
  return [head + tail.toLowerCase(), head + tail.toUpperCase()]
}

/**
 * Menu items. The shortcut labels match keys that ACTUALLY work: headings, paragraph and code
 * block are handled by StarterKit, lists and the quote by our flat nodes (blocks/), whose
 * shortcuts were chosen to match the disabled StarterKit nodes.
 *
 * `features` filters out items this field does not have: the menu must show what will work, not
 * the full catalogue with half of the rows dead.
 */
export function createSlashItems(t: (key: string) => string, features?: FeatureSet): SlashItem[] {
  const items: SlashItem[] = [
    {
      id: 'paragraph', group: 1, icon: IconAlignLeft, feature: null,
      title: t('common.editor.slash.paragraph'), keys: 'Mod-Alt-0',
      keywords: ['text', 'p', 'текст', 'абзац'],
      run: (editor, range) => at(editor, range).setParagraph().run(),
    },
    {
      id: 'h1', group: 2, icon: IconH1, feature: 'heading',
      title: t('common.editor.slash.h1'), keys: 'Mod-Alt-1',
      keywords: ['h1', 'heading', 'заголовок'],
      run: (editor, range) => at(editor, range).toggleHeading({ level: 1 }).run(),
    },
    {
      id: 'h2', group: 2, icon: IconH2, feature: 'heading',
      title: t('common.editor.slash.h2'), keys: 'Mod-Alt-2',
      keywords: ['h2', 'heading', 'заголовок'],
      run: (editor, range) => at(editor, range).toggleHeading({ level: 2 }).run(),
    },
    {
      id: 'h3', group: 2, icon: IconH3, feature: 'heading',
      title: t('common.editor.slash.h3'), keys: 'Mod-Alt-3',
      keywords: ['h3', 'heading', 'заголовок'],
      run: (editor, range) => at(editor, range).toggleHeading({ level: 3 }).run(),
    },
    {
      id: 'bulletList', group: 3, icon: IconList, feature: 'list',
      title: t('common.editor.slash.bulletList'), keys: 'Mod-Shift-8',
      keywords: ['list', 'bullet', 'список', 'маркированный'],
      run: (editor, range) => at(editor, range).toggleFlatList({ ordered: false, checked: null }).run(),
    },
    {
      id: 'orderedList', group: 3, icon: IconListNumbers, feature: 'list',
      title: t('common.editor.slash.orderedList'), keys: 'Mod-Shift-7',
      keywords: ['ordered', 'number', 'нумерованный'],
      run: (editor, range) => at(editor, range).toggleFlatList({ ordered: true, checked: null }).run(),
    },
    {
      id: 'taskList', group: 3, icon: IconListCheck, feature: 'list',
      title: t('common.editor.slash.taskList'), keys: 'Mod-Shift-9',
      keywords: ['task', 'todo', 'check', 'чек', 'задача'],
      run: (editor, range) => at(editor, range).toggleFlatList({ ordered: false, checked: false }).run(),
    },
    {
      id: 'quote', group: 4, icon: IconBlockquote, feature: 'quote',
      title: t('common.editor.slash.quote'), keys: 'Mod-Shift-b',
      keywords: ['quote', 'цитата', 'врезка'],
      run: (editor, range) => at(editor, range).toggleNode('quote', 'paragraph').run(),
    },
    {
      id: 'codeBlock', group: 4, icon: IconSourceCode, feature: 'codeBlock',
      title: t('common.editor.slash.codeBlock'), keys: 'Mod-Alt-c',
      keywords: ['code', 'код', 'fence'],
      run: (editor, range) => at(editor, range).toggleCodeBlock().run(),
    },
    // Inserted with a starter source and opened for editing at once: an empty diagram draws
    // nothing, and the person who asked for one is about to type its source anyway.
    {
      id: 'diagram', group: 4, icon: IconSchema, feature: 'diagram',
      title: t('common.editor.slash.diagram'), keys: null,
      keywords: ['diagram', 'mermaid', 'flowchart', 'схема', 'диаграмма'],
      run: (editor, range) => at(editor, range).insertDiagram().run(),
    },
    {
      id: 'divider', group: 4, icon: IconSeparatorHorizontal, feature: 'divider',
      title: t('common.editor.slash.divider'), keys: null,
      keywords: ['hr', 'divider', 'разделитель'],
      run: (editor, range) => at(editor, range).setHorizontalRule().run(),
    },
    // A group of its own: the table is the only block that does not fit on one markdown line, and
    // in the menu it also stands apart from the single-line ones.
    {
      id: 'table', group: 5, icon: IconTable, feature: 'table',
      title: t('common.editor.slash.table'), keys: null,
      keywords: ['table', 'таблица', 'grid'],
      run: (editor, range) => at(editor, range).insertTable({ rows: 2, cols: 3 }).run(),
    },
  ]

  if (!features) return items
  return items.filter((item) => item.feature === null || features.has(item.feature))
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
  /** The range of the typed `/query` while the menu is open. `null` — the menu is closed. */
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
  // The range is not only for mouse picks: a keyboard shortcut also uses it to remove the typed
  // `/query`, otherwise the command would apply and the slash would stay in the text.
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

  // Above the rest: while the menu is open, a shortcut must pass through us — otherwise the
  // command fires first, and there is nothing left to remove the `/query` with.
  priority: 1000,

  addOptions() {
    return { controller: null, items: null }
  },

  // The same shortcuts as labelled in the menu, with one addition: when the menu is open they
  // first close it, deleting the typed `/query`. A closed menu is not their business — the handler
  // returns false, and the regular binding from blocks.ts or StarterKit takes over.
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
        // In a code block a slash is a slash: a path, a regex, a comment. The menu there is not
        // just superfluous but dangerous — any of its commands would change the block type and
        // wreck the code.
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
