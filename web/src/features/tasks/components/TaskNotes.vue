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
// Order is changed by dragging a card by its handle, and saved whole: in a grid a card has no
// single neighbour to name, so "after which one" is not enough to say where it landed.
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useDraggable } from 'vue-draggable-plus'

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
      variant="outlined"
      rounded="lg"
      link
      @click="emit('open', note.code)"
    >
      <div class="task-note__head">
        <span class="task-note__title" :title="note.title">{{ note.title }}</span>
        <DragHandle v-if="!props.disabled" :label="t('tasks.note.drag')" @click.stop />
      </div>
      <p v-if="note.description" class="task-note__description">{{ note.description }}</p>
      <!-- Deleting is rare and asks first, so it is a quiet word in the corner, not a menu. -->
      <button v-if="!props.disabled" type="button" class="task-note__delete" @click.stop="ask(note)">
        {{ t('tasks.note.delete') }}
      </button>
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

/* 16px on the left, as in the cards above: the note's title stands on the line of theirs. The right
   side is tighter — the handle's own box makes up the rest. */
.task-note {
  position: relative;
  display: flex;
  flex-direction: column;
  gap: 6px;
  min-height: 72px;
  padding: 12px 8px 12px 16px;
}

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
.task-note__description {
  margin: 0 8px 0 0;
  font-size: 13px;
  line-height: 1.45;
  color: var(--text-muted);
  display: -webkit-box;
  -webkit-line-clamp: 3;
  line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

/* A text button in the small type of a mark, shown only on the card under the pointer — a delete
   on every card at once would be louder than the notes — and red only when aimed at. It is pinned
   to the bottom-right corner, out of the flow: the card is as tall as its title and description,
   and delete lines up across a row of cards of different text lengths. */
.task-note__delete {
  opacity: 0;
  position: absolute;
  right: 12px;
  bottom: 6px;
  /* Over the description's last line, the card's own surface with a short fade on the left: a long
     description slides under the word instead of running into it. */
  padding: 2px 0 2px 24px;
  background: linear-gradient(
    to right,
    transparent,
    rgb(var(--v-theme-surface)) 20px
  );
  font: inherit;
  font-size: 11px;
  line-height: 1;
  color: var(--text-faint);
  border: none;
  cursor: pointer;
  transition: opacity 0.18s ease, color 0.12s ease;
}

/* Keyboard too: Tab into the card brings it out the same way the pointer does. */
.task-note:hover .task-note__delete,
.task-note:focus-within .task-note__delete { opacity: 1; }

.task-note__delete:hover,
.task-note__delete:focus-visible { color: var(--error); }

/* A finger does not hover: on a touch screen it stays visible, as the drag handle does. */
@media (hover: none) {
  .task-note__delete { opacity: 1; }
}

.task-note--ghost { opacity: 0.4; }
</style>
