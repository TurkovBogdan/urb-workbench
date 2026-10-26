<script setup lang="ts">
// The file navigation of the codex materials: one level of the canvas tree, rendering its children
// with itself. The roots are the codexes mounted into the workspace; below them their notes, at
// most four levels in all. A click opens a row; a double click on a row with children folds or
// unfolds it — and only that, it does not open it (see `onRowClick`). The chevron folds too. Which
// rows are folded is the page's (`collapsed`), so it outlives a re-read of the tree.
//
// Every row has its menu: add a note under it (not on the fourth level), move a note up or down
// among its siblings, move it under another parent, delete it. A codex row has only "add": the
// codex itself is edited, unmounted and deleted among the available codexes.
//
// DRAGGING. A note is dragged by its whole row — a handle would cost every note row its width in
// a narrow navigation; a short movement stays a click (`fallbackTolerance`), and the row's buttons
// never start a gesture. Each level is its own sortable container, all in one group, so a note
// moves among its siblings, under another parent and into another codex. The codexes themselves
// stay put: the top level neither gives nor takes. A container lets in only what the tree's rules
// allow (`accepts`) — a move bound to be refused is never offered. A codex row also takes a note
// (`CodexDropZone`): a codex with no notes, or a folded one, has no row of notes to drop into.
//
// The gesture is built on Pointer Events (`forceFallback`), as in the task list: native DnD sends
// nothing for a finger and gives no control over the preview.
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useDraggable } from 'vue-draggable-plus'
import {
  IconArrowDown,
  IconArrowUp,
  IconArrowsMove,
  IconBook2,
  IconCheck,
  IconChevronRight,
  IconCopy,
  IconFileExport,
  IconFileText,
  IconFolder,
  IconFolderOpen,
  IconPlus,
  IconRestore,
  IconTrash,
} from '@tabler/icons-vue'

import ActionMenu, { type ActionMenuItem } from '@/components/ActionMenu.vue'
import { startDownload } from '@/components/files/download'
import IconSwatch from '@/components/IconSwatch.vue'
import { useClipboard } from '@/composables/useClipboard'
import { colorVarsByName } from '@/shared/colors'

import CodexDropZone from './CodexDropZone.vue'
import { codexExportUrl, type TreeNode } from '../api'
import { anchorAfterDrop, type NoteDrop } from '../drag'
import { CODEX_DEPTH_MAX } from '../labels'

/** Duration of the sibling reorder animation — the library's stock FLIP, as in the task list. */
const ANIMATION_MS = 150
/** On a touch screen a hold, not a movement, starts the gesture — otherwise it steals scrolling. */
const TOUCH_HOLD_MS = 250

const props = withDefaults(
  defineProps<{
    nodes: TreeNode[]
    selected: string
    collapsed: Set<string>
    depth?: number
    /** The codex or note these nodes hang under; empty on the top level, the codexes. */
    parentCode?: string
    /**
     * Notes can be dragged. Off on a filtered tree: it shows a selection, not the layout, and a
     * place next to a visible neighbour would mean something other than what the person sees.
     */
    reorderable?: boolean
    /** Whether a note may land under a parent — the tree's rules, asked before a drop is offered. */
    accepts: (parent: string, code: string) => boolean
    /**
     * The color of the codex these notes belong to. Empty on the top level and for a codex without
     * a color — then everything falls back to the app accent.
     */
    tone?: string
  }>(),
  { depth: 1, parentCode: '', reorderable: true, tone: '' },
)

// Each tree item carries its codex's color as `.color-tones` vars, and everything inside reads
// them: the folder and file icons, the selected row, the drag placeholder, the preview — even the
// preview cloned onto `<body>` keeps them, since they sit inline on the item it clones. A codex
// item takes its own color, a note its codex's.
const toneOf = (node: TreeNode) => (props.depth === 1 ? node.color : props.tone)

const emit = defineEmits<{
  select: [node: TreeNode]
  toggle: [node: TreeNode]
  add: [node: TreeNode]
  move: [node: TreeNode]
  up: [node: TreeNode]
  down: [node: TreeNode]
  remove: [node: TreeNode]
  restore: [node: TreeNode]
  drop: [drop: NoteDrop]
  dragging: [on: boolean]
}>()

const { t } = useI18n()
const { copy, isCopied } = useClipboard()
const openMenu = ref<string | null>(null)

const container = ref<HTMLElement | null>(null)

// The list the library moves around; the tree renders `nodes`, which stay the source of truth.
const codes = ref<string[]>([])

watch(
  () => props.nodes,
  (nodes) => { codes.value = nodes.map((node) => node.code) },
  { immediate: true },
)

const isTopLevel = props.depth === 1

const sortable = useDraggable(container, codes, {
  group: {
    name: 'codex-notes',
    pull: !isTopLevel,
    put: isTopLevel
      ? false
      : (_to, _from, dragged) => {
          const code = (dragged as HTMLElement).dataset.code
          return !!code && props.accepts(props.parentCode, code)
        },
  },
  sort: !isTopLevel,
  draggable: '.codex-tree__item--note',
  // A row belongs to THE container it sits in — without this every enclosing level starts the
  // gesture too, and nothing moves. The row's own buttons are filtered out as well: a press on the
  // chevron, "add" or the menu is never the start of a drag.
  filter: (event: Event) => {
    const target = event.target as HTMLElement | null
    return target?.closest('.codex-tree') !== container.value || !!target?.closest('button, .v-btn')
  },
  preventOnFilter: false,
  animation: ANIMATION_MS,
  forceFallback: true,
  fallbackOnBody: true,
  fallbackTolerance: 4,
  delay: TOUCH_HOLD_MS,
  delayOnTouchOnly: true,
  ghostClass: 'codex-drag--ghost',
  chosenClass: 'codex-drag--chosen',
  fallbackClass: 'codex-drag--preview',
  scroll: true,
  scrollSensitivity: 60,
  onStart: () => emit('dragging', true),
  onEnd: (event) => {
    emit('dragging', false)
    const code = (event.item as HTMLElement).dataset.code
    const to = event.to as HTMLElement
    const parent = to.dataset.parent
    if (!code || !parent) return
    // Lifted and put back, or dropped on the row of the codex it already tops: nothing moved, and
    // "after the neighbour above" for an untouched note would be a reorder nobody asked for.
    if (to === event.from && event.oldIndex === event.newIndex) return
    if (to.dataset.drop === 'end' && parent === props.parentCode) return
    emit('drop', { code, parent, after: anchorAfterDrop(to, code, event.newIndex) })
  },
})

watch(
  () => props.reorderable && !isTopLevel,
  (on) => { if (on) sortable.resume(); else sortable.pause() },
  { immediate: true },
)

/** The last live top-level note of a codex — where a note dropped on the codex row lands after. */
function lastChild(node: TreeNode): string | null {
  const live = node.children.filter((child) => !child.deleted)
  return live[live.length - 1]?.code ?? null
}

// A deleted note (shown on request) has one action — coming back where it stood, with whatever
// left with it. Up and down count live siblings only: a deleted one holds no place in the row.
const liveNodes = computed(() => props.nodes.filter((node) => !node.deleted))

function items(node: TreeNode): ActionMenuItem[] {
  if (node.deleted) {
    return [{ key: 'restore', icon: IconRestore, label: t('codex.list.restore'), run: () => emit('restore', node) }]
  }
  const list: ActionMenuItem[] = []
  if (props.depth < CODEX_DEPTH_MAX) {
    list.push({ key: 'add', icon: IconPlus, label: t('codex.tree.add'), hotkey: 'N', run: () => emit('add', node) })
  }
  // A codex row: its archive is the whole codex; the browser takes it, the server names the file.
  if (props.depth === 1) {
    list.push({
      key: 'export',
      icon: IconFileExport,
      label: t('codex.transfer.export'),
      divider: true,
      run: () => startDownload(codexExportUrl(node.code), ''),
    })
    return list
  }
  const at = liveNodes.value.indexOf(node)
  list.push(
    { key: 'up', icon: IconArrowUp, label: t('codex.tree.up'), disabled: at === 0, run: () => emit('up', node) },
    { key: 'down', icon: IconArrowDown, label: t('codex.tree.down'), disabled: at === liveNodes.value.length - 1, run: () => emit('down', node) },
    { key: 'move', icon: IconArrowsMove, label: t('codex.tree.move'), run: () => emit('move', node) },
    { key: 'delete', icon: IconTrash, label: t('codex.tree.delete'), danger: true, hotkey: 'D', run: () => emit('remove', node) },
  )
  return list
}

const isOpen = (node: TreeNode) => node.children.length > 0 && !props.collapsed.has(node.code)

// ── Click and double click ────────────────────────────────────────────────────
// A double click arrives as two clicks first, so the first one of a pair would open the row before
// the double click could fold it. A row with children therefore waits out the double-click window
// before it opens, and a second click inside the window cancels the open. A row without children
// has nothing to fold — it opens at once.
const DOUBLE_CLICK_MS = 200
let pendingOpen: ReturnType<typeof setTimeout> | null = null

function cancelPendingOpen() {
  if (pendingOpen) clearTimeout(pendingOpen)
  pendingOpen = null
}

function onRowClick(node: TreeNode, event: MouseEvent) {
  cancelPendingOpen()
  // A deleted note is not opened: its page would only refuse every edit. Its menu restores it.
  if (node.deleted) return
  if (!node.children.length) {
    emit('select', node)
    return
  }
  if (event.detail > 1) return
  pendingOpen = setTimeout(() => {
    pendingOpen = null
    emit('select', node)
  }, DOUBLE_CLICK_MS)
}

function onRowDblclick(node: TreeNode) {
  cancelPendingOpen()
  if (node.children.length) emit('toggle', node)
}

onBeforeUnmount(cancelPendingOpen)
</script>

<template>
  <ul
    ref="container"
    class="codex-tree"
    :class="{ 'codex-tree--root': depth === 1 }"
    :data-parent="parentCode || undefined"
  >
    <li
      v-for="node in nodes"
      :key="node.code"
      class="codex-tree__item"
      :class="{
        'codex-tree__item--note': depth > 1 && !node.deleted,
        'codex-tree__item--deleted': node.deleted,
        'color-tones': toneOf(node),
      }"
      :style="toneOf(node) ? colorVarsByName(toneOf(node)) : undefined"
      :data-code="node.code"
    >
      <!-- A codex row is also a drop target; a note row is wrapped in a plain block. -->
      <component
        :is="depth === 1 ? CodexDropZone : 'div'"
        v-bind="depth === 1 ? { codex: node.code, after: lastChild(node), accepts } : {}"
      >
        <div
          class="codex-tree__row"
          :class="{ 'codex-tree__row--selected': node.code === selected }"
          @click="onRowClick(node, $event)"
          @dblclick="onRowDblclick(node)"
          @contextmenu.prevent="openMenu = node.code"
        >
          <!-- The chevron keeps its place on a leaf too, so the icons of one level stand in a column. -->
          <button
            v-if="node.children.length"
            type="button"
            class="codex-tree__chevron"
            :class="{ 'codex-tree__chevron--open': isOpen(node) }"
            :aria-label="isOpen(node) ? t('codex.tree.collapse') : t('codex.tree.expand')"
            :aria-expanded="isOpen(node)"
            @click.stop="emit('toggle', node)"
            @dblclick.stop
          >
            <IconChevronRight :size="14" />
          </button>
          <span v-else class="codex-tree__chevron codex-tree__chevron--leaf" />

          <!-- A codex root wears its look, as its row among the available codexes does. -->
          <IconSwatch v-if="depth === 1 && node.icon" :icon="node.icon" :color="node.color" :width="18" />
          <IconBook2 v-else-if="depth === 1" :size="16" class="codex-tree__icon" />
          <!-- A deleted note wears the trash instead of its folder or file — the icon column says
               "deleted" before the struck-through title is read; no codex color, it is out of it. -->
          <IconTrash v-else-if="node.deleted" :size="16" class="codex-tree__icon" />
          <component
            :is="isOpen(node) ? IconFolderOpen : node.children.length ? IconFolder : IconFileText"
            v-else
            :size="16"
            class="codex-tree__icon"
            :class="{ 'codex-tree__icon--toned': tone }"
          />
          <span class="codex-tree__title">{{ node.title }}</span>
          <!-- The record's CODEX@ code to the clipboard — what a task, a journal entry or the agent
               refers to it by. Adding a note is in the row's menu and the page header. -->
          <VBtn
            icon
            variant="text"
            size="x-small"
            class="codex-tree__copy"
            :title="t('common.action.copy_code')"
            :aria-label="t('common.action.copy_code')"
            @click.stop="copy(node.code)"
            @dblclick.stop
          >
            <IconCheck v-if="isCopied(node.code)" :size="14" />
            <IconCopy v-else :size="14" />
          </VBtn>
          <ActionMenu
            class="codex-tree__menu"
            :open="openMenu === node.code"
            :items="items(node)"
            :code="node.code"
            :label="t('codex.tree.actions')"
            @update:open="(open) => (openMenu = open ? node.code : null)"
            @click.stop
            @dblclick.stop
          />
        </div>
      </component>
      <CodexTree
        v-if="isOpen(node)"
        :nodes="node.children"
        :selected="selected"
        :collapsed="collapsed"
        :depth="depth + 1"
        :parent-code="node.code"
        :tone="depth === 1 ? node.color : tone"
        :reorderable="reorderable"
        :accepts="accepts"
        @select="(n) => emit('select', n)"
        @toggle="(n) => emit('toggle', n)"
        @add="(n) => emit('add', n)"
        @move="(n) => emit('move', n)"
        @up="(n) => emit('up', n)"
        @down="(n) => emit('down', n)"
        @remove="(n) => emit('remove', n)"
        @restore="(n) => emit('restore', n)"
        @drop="(d) => emit('drop', d)"
        @dragging="(on) => emit('dragging', on)"
      />
    </li>
  </ul>
</template>

<style scoped>
.codex-tree {
  list-style: none;
  margin: 0;
  padding: 0 0 0 12px;
}

.codex-tree--root { padding-left: 0; }

.codex-tree__row {
  display: flex;
  align-items: center;
  gap: 4px;
  min-height: 30px;
  padding: 0 4px 0 2px;
  border-radius: 6px;
  /* The app's text token, as the record's cards beside it: inherited, the row took Vuetify's
     surface color, which follows Vuetify's theme rather than ours. */
  color: var(--text);
  cursor: pointer;
  /* A double click folds the row; without this it would also select the title's word. */
  user-select: none;
}

.codex-tree__row:hover { background: var(--surface-hover, rgba(127, 127, 127, 0.08)); }

/* The open row in its codex's color; a codex without one — the app accent. */
.codex-tree__row--selected {
  background: var(--gc-fill, var(--accent-soft));
  color: var(--gc-ink, var(--accent));
}

.codex-tree__chevron {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex: none;
  width: 18px;
  height: 18px;
  padding: 0;
  border: 0;
  border-radius: 4px;
  background: none;
  color: inherit;
  cursor: pointer;
  opacity: 0.7;
  transition: transform 0.12s ease;
}

.codex-tree__chevron:hover { opacity: 1; }
.codex-tree__chevron--open { transform: rotate(90deg); }
.codex-tree__chevron--leaf { cursor: default; }

.codex-tree__icon { flex: none; opacity: 0.75; }

/* A note's icon in its codex's color — the readable tone of the active theme, at full strength:
   faded, a hue would read as a muddy grey. */
.codex-tree__icon--toned {
  color: var(--gc-ink);
  opacity: 1;
}

.codex-tree__title {
  flex: 1;
  min-width: 0;
  font-size: 13px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.codex-tree__menu { flex: none; }

/* A deleted note, shown on request: muted as a whole and struck through, so it never reads as a
   live one; the pointer is the default one — the row does not open. Hover restores it to full
   strength, reading it does not require restoring it. */
.codex-tree__item--deleted > * > .codex-tree__row {
  opacity: 0.55;
  cursor: default;
}

.codex-tree__item--deleted > * > .codex-tree__row:hover { opacity: 1; }

.codex-tree__item--deleted > * > .codex-tree__row .codex-tree__title {
  text-decoration: line-through;
}

/* "Copy the code" shows on the row under the pointer and on the open one. */
.codex-tree__copy { flex: none; opacity: 0; }

/* Tight against the menu's dots: the two are one cluster of row actions, and the stock x-small
   button plus the row gap left a hole between them. */
.codex-tree__copy.v-btn {
  width: 24px;
  min-width: 24px;
  height: 24px;
  margin-inline-end: -4px;
}
.codex-tree__row:hover .codex-tree__copy,
.codex-tree__row--selected .codex-tree__copy { opacity: 1; }

/* ── Dragging ──────────────────────────────────────────────────────────────────
   The place it will land: the source stays where it was, faded on its codex's color — where it
   was taken from and where it comes back to if let go nowhere. */
.codex-drag--ghost > * > .codex-tree__row {
  opacity: 0.4;
  background: var(--gc-fill, var(--accent-soft));
}
</style>

<!-- Not `scoped`: with `fallbackOnBody` the preview is a clone appended straight to `<body>`, where no
     scope attribute of this component reaches it. The rules keyed on the body's class live here too:
     in a scoped block `:global(body.x) .y` compiles to a bare `body.x` — the rest of the selector is
     dropped, and a rule meant for a row lands on the whole page. -->
<style>
/* While a note is held no row reacts to hover — a highlight would read as "drop here". */
body.codex-dragging .codex-tree__row:hover { background: transparent; }
body.codex-dragging .codex-tree__copy { opacity: 0; }

/* The preview under the cursor — the note with its whole branch, as it will land — lifted by a
   shadow and edged in its codex's color. SortableJS writes its opacity and transform inline on
   the clone itself. */
.codex-drag--preview {
  list-style: none;
  background: var(--surface);
  border: 1px solid var(--gc-ink, var(--accent));
  border-radius: 6px;
  box-shadow: 0 12px 32px rgba(0, 0, 0, 0.28);
  cursor: grabbing;
}
</style>
