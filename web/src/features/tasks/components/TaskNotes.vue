<script setup lang="ts">
// The task's notes under the plan — a section header, then cards two to a row, a title and a
// description each.
//
// A note is planning material: a schema, a breakdown of options, a concept the plan rests on.
// So it sits right under the plan (under the context on a simple task, which has no plan).
//
// The card shows what the note is about — never its text: a task with three long documents would
// otherwise be a page of documents. The text opens on the note's own page.
//
// The add button sits in the header, the way the journal and subtasks have theirs, and is there
// also when there are no notes: a person writes notes too, not only the agent. Adding creates a
// placeholder note and opens it at once — the page is the form.
//
// A card reads like every other entry in the app: the handle leads it, the "⋯" closes its title
// line, and a right click anywhere on the card opens the same menu.
//
// Order is changed by dragging a card by its handle, and saved whole: in a grid a card has no
// single neighbour to name, so "after which one" is not enough to say where it landed.
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'
import { useDraggable } from 'vue-draggable-plus'
import { IconArrowBack, IconArrowForward, IconExternalLink, IconFileText, IconTrash } from '@tabler/icons-vue'

import ActionMenu, { type ActionMenuItem } from '@/components/ActionMenu.vue'
import ConfirmDialog from '@/components/ConfirmDialog.vue'
import DragHandle from '@/components/DragHandle.vue'

import CollectionHeader from './CollectionHeader.vue'
import { createTaskNote, deleteTaskNote, reorderTaskNotes, type TaskNoteRow } from '../api'

/** Duration of the reorder animation — the library's stock FLIP. */
const ANIMATION_MS = 150

const props = defineProps<{
  taskCode: string
  notes: TaskNoteRow[]
  /** The task is deleted: its notes are read, not added, moved or deleted. */
  disabled?: boolean
}>()

const emit = defineEmits<{
  /** A note to open — the page flushes what was typed before it leaves. */
  open: [code: string]
  /** The list changed here; the task is re-read, its response carries the list. */
  changed: []
}>()

const { t } = useI18n()
const router = useRouter()

// ── Order ─────────────────────────────────────────────────────────────────────
// The cards render a local copy of the list, and the library reorders THAT copy the moment the
// card is dropped. The save goes out after, and a successful one changes nothing on screen: the
// screen already shows what was sent. Rendering the task's own list instead made a drop jump —
// the cards snapped back to the old order, then forward again when the task was re-read.
// A fresh list from the task (a re-read, the agent's edit) replaces the copy.
const grid = ref<HTMLElement | null>(null)
const items = ref<TaskNoteRow[]>([])

watch(() => props.notes, (notes) => { items.value = [...notes] }, { immediate: true })

const sortable = useDraggable(grid, items, {
  handle: '.drag-handle',
  draggable: '.task-note',
  animation: ANIMATION_MS,
  // Pointer Events rather than native DnD, as in the task list: it works with a finger too and
  // gives the preview to us, not to the browser.
  forceFallback: true,
  fallbackOnBody: true,
  fallbackTolerance: 4,
  ghostClass: 'task-note--ghost',
  onEnd: (event) => {
    if (event.oldIndex === event.newIndex) return
    void saveOrder()
  },
})

watch(() => props.disabled, (off) => { if (off) sortable.pause(); else sortable.resume() }, { immediate: true })

/** The order on screen goes out as is; only a refused save re-reads the task to show the real one. */
async function saveOrder(): Promise<void> {
  try {
    await reorderTaskNotes(props.taskCode, items.value.map((note) => note.code))
  } catch {
    emit('changed')
  }
}

/** Moving without a mouse: one place back or forward in the grid, saved the way a drop is. */
function shift(code: string, step: -1 | 1): void {
  const from = items.value.findIndex((note) => note.code === code)
  const to = from + step
  if (from < 0 || to < 0 || to >= items.value.length) return
  const next = [...items.value]
  const [note] = next.splice(from, 1)
  next.splice(to, 0, note)
  items.value = next
  void saveOrder()
}

// ── Add ───────────────────────────────────────────────────────────────────────
const adding = ref(false)

async function add(): Promise<void> {
  adding.value = true
  try {
    const note = await createTaskNote(props.taskCode, t('tasks.note.new_title'))
    emit('changed')
    emit('open', note.code)
  } finally {
    adding.value = false
  }
}

// ── Delete ────────────────────────────────────────────────────────────────────
// A note leaves the task in one click from a menu — so it asks first. The action outlives the open
// flag: while the dialog fades out it keeps its own text.
const removing = ref<TaskNoteRow | null>(null)
const confirmOpen = ref(false)

function ask(note: TaskNoteRow): void {
  removing.value = note
  confirmOpen.value = true
}

async function remove(): Promise<void> {
  confirmOpen.value = false
  const note = removing.value
  if (!note) return
  try {
    await deleteTaskNote(props.taskCode, note.code)
  } finally {
    emit('changed')
  }
}

const confirmText = computed(() =>
  t('tasks.note.delete_confirm.text', { title: removing.value?.title ?? '' }),
)

// ── Menu ──────────────────────────────────────────────────────────────────────
// The same items in the same order as a task row's menu: the ways to open first, then the rest. The
// list keeps only whose menu is open, to mark that card while the pointer is on the items.
const openMenu = ref<string | null>(null)
const menus = new Map<string, InstanceType<typeof ActionMenu>>()

function setMenu(code: string, open: boolean): void {
  if (open) openMenu.value = code
  else if (openMenu.value === code) openMenu.value = null
}

function bindMenu(code: string, menu: unknown): void {
  if (menu) menus.set(code, menu as InstanceType<typeof ActionMenu>)
  else menus.delete(code)
}

function openInNewTab(note: TaskNoteRow): void {
  const { href } = router.resolve({ name: 'tasks-task-note', params: { code: props.taskCode, note: note.code } })
  window.open(href, '_blank', 'noopener')
}

function menuItems(note: TaskNoteRow): ActionMenuItem[] {
  const menu: ActionMenuItem[] = [
    { key: 'open', icon: IconFileText, label: t('tasks.note.open'), hotkey: 'E', run: () => emit('open', note.code) },
    { key: 'open-tab', icon: IconExternalLink, label: t('tasks.note.open_new_tab'), hotkey: 'T', run: () => openInNewTab(note) },
  ]
  if (props.disabled) return menu
  // W and S move, as on a task row; in a grid "up" is the place before, "down" the place after.
  const at = items.value.findIndex((candidate) => candidate.code === note.code)
  menu.push(
    { key: 'delete', icon: IconTrash, label: t('tasks.note.delete'), danger: true, hotkey: 'D', divider: true, run: () => ask(note) },
    { key: 'back', icon: IconArrowBack, label: t('tasks.note.move_back'), hotkey: 'W', divider: true, disabled: at === 0, run: () => shift(note.code, -1) },
    { key: 'forward', icon: IconArrowForward, label: t('tasks.note.move_forward'), hotkey: 'S', disabled: at === items.value.length - 1, run: () => shift(note.code, 1) },
  )
  return menu
}
</script>

<template>
  <section class="task-notes-section">
    <CollectionHeader
      :title="t('tasks.note.section')"
      :hint="t('tasks.note.hint.section')"
      :add-label="props.disabled ? undefined : t('tasks.note.add')"
      :adding="adding"
      :empty="!items.length"
      @add="add"
    />

    <!-- Always in the markup, empty or not: the sortable is bound to this element once, at mount. -->
    <div ref="grid" class="task-notes" :aria-label="t('tasks.note.list')">
    <VCard
      v-for="note in items"
      :key="note.code"
      :data-code="note.code"
      class="task-note drag-row"
      :class="{ 'task-note--menu': openMenu === note.code }"
      variant="outlined"
      rounded="lg"
      link
      @click="emit('open', note.code)"
      @contextmenu="menus.get(note.code)?.openAt($event)"
    >
      <div class="task-note__head">
        <DragHandle
          class="task-note__handle"
          :class="{ 'task-note__handle--off': props.disabled }"
          :label="t('tasks.note.drag')"
          always
          @click.stop
        />
        <span class="task-note__title" :title="note.title">{{ note.title }}</span>
        <ActionMenu
          :ref="(menu) => bindMenu(note.code, menu)"
          class="task-note__menu"
          :open="openMenu === note.code"
          :items="menuItems(note)"
          :code="note.code"
          :label="t('tasks.note.actions')"
          @update:open="setMenu(note.code, $event)"
        />
      </div>
      <p v-if="note.description" class="task-note__description">{{ note.description }}</p>
    </VCard>
    </div>

    <ConfirmDialog
      v-model="confirmOpen"
      :title="t('tasks.note.delete_confirm.title')"
      :text="confirmText"
      :confirm-label="t('tasks.note.delete_confirm.confirm')"
      enter-confirms
      focus-confirm
      @confirm="remove"
    />
  </section>
</template>

<style scoped>
/* Two to a row: half of the plan column holds a title and a few lines about it without cutting
   them to a word. Narrow screens — one. */
.task-notes {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}

@media (max-width: 600px) {
  .task-notes { grid-template-columns: minmax(0, 1fr); }
}

/* Both sides are tight: the handle's box on the left and the "⋯" button's on the right make up the
   rest of the padding. The gap is small because the title line is already taller than its text —
   the handle and the "⋯" stretch it to 28px. */
.task-note {
  position: relative;
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-height: 72px;
  padding: 12px 8px;
}

/* The handle leads the title line, centred on its first line — the head aligns to the top, and the
   handle's box is as tall as the title's line with its padding. It is always shown, not only under
   the pointer: a gap before every title would read as a broken indent. On a deleted task's note,
   which cannot be moved, it keeps its place unseen, so the title stands where it does elsewhere. */
.task-note__handle--off { visibility: hidden; }

/* While its menu is open the card stays as it looks under the pointer: the pointer has gone onto
   the items, and only this mark says which note they will act on. */
.task-note--menu { border-color: var(--gc-ink, var(--accent)); }

.task-note__head {
  display: flex;
  align-items: flex-start;
  gap: 4px;
  min-width: 0;
}

/* Two lines before the ellipsis: a long title still leaves the card its description. */
.task-note__title {
  flex: 1;
  min-width: 0;
  padding-top: 4px;
  font-size: 14px;
  font-weight: 600;
  line-height: 1.35;
  overflow-wrap: anywhere;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

/* Three lines at most: the description says what the note is and when to open it, and a card
   taller than its neighbours breaks the row. */
/* Exactly under the title: on the left past the handle (its 20px box plus the head's 4px gap), on
   the right short of the "⋯" column (its 28px box plus the same gap) — the text forms one block
   with the title instead of running under the button. */
.task-note__description {
  margin: 0 32px 0 24px;
  font-size: 13px;
  line-height: 1.45;
  color: var(--text-muted);
  display: -webkit-box;
  -webkit-line-clamp: 3;
  line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.task-note--ghost { opacity: 0.4; }
</style>
