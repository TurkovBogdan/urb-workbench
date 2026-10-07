<script setup lang="ts">
// The root row of one group card and dragging between cards.
//
// A separate component rather than a piece of the list, for exactly one reason: a sortable is
// created ON A CONTAINER, and there are as many containers as cards. The composable lives in
// setup, and there is no other way to call it for a variable number of sections. For the same
// reason one parent's children live in their own component (`TaskSubtree`): they have their own
// container and their own sibling row.
//
// THE WHOLE BRANCH IS DRAGGED: a root moves together with its subtasks because they sit inside its
// wrapper.
//
// The gesture is built on Pointer Events (`forceFallback: true`), not native HTML5 DnD. Native DnD
// is justified only for files from the OS and moves between windows: it sends no events for a
// finger in any mobile browser, gives no control over the preview and blocks scrolling during the
// gesture.
//
// A row is grabbed by its HANDLE, not as a whole: otherwise the gesture steals text selection from
// the row, and on a touch device — list scrolling.
//
// The mouse is not the only way: the same moves exist as row menu items. This is not a nicety but
// a requirement — WCAG 2.2 SC 2.5.7 asks for a single-pointer alternative to dragging, and a menu
// that opens from the keyboard covers SC 2.1.1 as well.
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useDraggable } from 'vue-draggable-plus'

import TaskRow from './TaskRow.vue'
import TaskSubtree from './TaskSubtree.vue'
import { anchorAfterDrop } from '../drag'
import { useTasksStore, type TaskSection } from '../stores/tasks.store'
import type { TaskListRow } from '../api'

/** Duration of the sibling reorder animation — the library's stock FLIP. */
const ANIMATION_MS = 150

const props = defineProps<{
  section: TaskSection
  /** Code of the task the person navigated to from the list: its row stays marked. */
  openCode?: string | null
  /** How many subtasks each task has — the list counts, this only displays. */
  childCounts: Map<string, number>
  /**
   * The order in these results can be changed.
   *
   * Off on a narrowed list: it shows a SELECTION, not the layout — branches are not drawn, not all
   * group siblings are on screen, and reordering relative to a visible neighbour would mean
   * something other than what the person sees. The handle is hidden then: a gesture that does
   * nothing is worse than an absent one.
   */
  reorderable?: boolean
}>()

const emit = defineEmits<{
  open: [code: string]
  edit: [task: TaskListRow]
  addChild: [task: TaskListRow]
  remove: [code: string]
  restore: [code: string]
  /**
   * The row moved: which row it landed under, which group it is in and whose child it is now.
   *
   * `group` absent — the group is untouched; `parent` absent — the parent is untouched, `null` —
   * detach. The same three keys go into one request: a single mouse movement must not show
   * intermediate states.
   */
  move: [payload: {
    code: string
    after: string | null
    group?: string | null
    parent?: string | null
  }]
}>()

const { t } = useI18n()
// The store is needed for one thing — whether the branch under a row is collapsed: that state
// lives there, next to the collapsed state of group cards, and holds until the workspace changes.
const store = useTasksStore()

/** Group key in markup: empty string — "No group", otherwise its code in `dataset` is indistinguishable from absence. */
const groupKey = computed(() => props.section.group?.code ?? '')

const container = ref<HTMLElement | null>(null)

// The list the library itself moves around. We render not it but `section.branches` from the
// store — that stays the source of truth, and this array exists for sortable to keep its state.
const codes = ref<string[]>([])

watch(
  () => props.section.branches,
  (branches) => { codes.value = branches.map((node) => node.task.code) },
  { immediate: true },
)

const sortable = useDraggable(container, codes, {
  // All cards share one sortable group name — that is what makes moving a task into another group
  // work. `put` is open: both roots from neighbouring cards and subtasks pulled out of branches
  // land here — the latter is detaching.
  group: { name: 'tasks', pull: true, put: true },
  handle: '.drag-handle',
  draggable: '.task-drag',
  // A handle belongs to THE container it sits in. Without this both sortables start the gesture at
  // once — the outer takes the branch, the inner the subtask — and nothing moves: two grabs fight
  // over one pointer. A selector cannot express this (`.task-subtree` would also filter out the
  // nested container itself with its rows), so a function decides: whose container is it.
  filter: (event: Event) =>
    (event.target as HTMLElement | null)?.closest('.task-subtree, .task-rows') !== container.value,
  animation: ANIMATION_MS,
  // Pointer Events instead of native DnD (see the file header).
  forceFallback: true,
  fallbackOnBody: true,
  ghostClass: 'task-drag--ghost',
  chosenClass: 'task-drag--chosen',
  dragClass: 'task-drag--drag',
  fallbackClass: 'task-drag--preview',
  // Grab threshold: a short movement over a row stays a click rather than starting a move.
  fallbackTolerance: 4,
  // Auto-scroll is needed when a card does not fit on screen entirely.
  scroll: true,
  scrollSensitivity: 80,
  onStart: () => { store.dragging = true },
  onEnd: (event) => {
    store.dragging = false
    const item = event.item as HTMLElement
    const code = item.dataset.code
    if (!code) return
    const to = event.to as HTMLElement
    const from = event.from as HTMLElement
    const sameContainer = to === from
    // The gesture ended where it started: the branch was lifted and put back. No request must be
    // sent for this — the position is named by a neighbour, and "after the neighbour above" for an
    // untouched row means a reorder nobody asked for.
    if (sameContainer && event.oldIndex === event.newIndex) return
    // Dropped onto the header of its OWN card: this cannot send it to the end of its own row — the
    // header means "into this group", and it is already there. A pointless gesture, not worth a
    // request.
    if (to.dataset.drop === 'end' && to.dataset.group === groupKey.value) return
    // Only a ROOT move arrives here — own or from a neighbouring card: `onEnd` goes to the sortable
    // the gesture started from, while a subtask pulled out of a branch is handled by its own
    // container (`TaskSubtree`), which also knows that this is a detach.
    emit('move', {
      code,
      after: anchorAfterDrop(to, code, event.newIndex),
      ...(sameContainer ? {} : { group: to.dataset.group || null }),
    })
  },
})

watch(
  () => props.reorderable !== false,
  (on) => { if (on) sortable.resume(); else sortable.pause() },
  { immediate: true },
)

// ── The same move without a mouse ─────────────────────────────────────────────
// "Up" — land after the one two places above: otherwise swapping with the neighbour changes
// nothing. "Down" — after the nearest neighbour below.

function neighbourFor(code: string, direction: -1 | 1): string | null | undefined {
  const order = props.section.branches.map((node) => node.task.code)
  const at = order.indexOf(code)
  if (at === -1) return undefined
  const target = at + direction
  if (target < 0 || target >= order.length) return undefined
  return direction === -1 ? (target > 0 ? order[target - 1] : null) : order[target]
}

function canStep(code: string, direction: -1 | 1): boolean {
  return neighbourFor(code, direction) !== undefined
}

function step(code: string, direction: -1 | 1): void {
  const after = neighbourFor(code, direction)
  if (after === undefined) return
  emit('move', { code, after })
}

/**
 * A move arrived from a branch. A reorder among siblings is passed on as is; a detach too, but if
 * no group was named (as with the menu item: it has no drop point), the card fills in its own — a
 * task cannot detach "into nowhere", it must land somewhere.
 */
function fromSubtree(payload: {
  code: string
  after: string | null
  parent?: string | null
  group?: string | null
}): void {
  if (payload.parent === null && !('group' in payload)) {
    emit('move', { ...payload, group: groupKey.value || null })
    return
  }
  emit('move', payload)
}
</script>

<template>
  <div
    ref="container"
    class="task-rows"
    :class="{ 'task-rows--empty': !section.branches.length }"
    :data-group="groupKey"
  >
    <!-- The empty-section caption sits INSIDE the sortable container, not next to it: a container
         without children would collapse to zero, leaving nothing to hit with a dragged branch.
         Only `.task-drag` elements are dragged, so the caption stays put and takes no part in the
         gesture — it only holds the height and explains why this card is here. -->
    <p v-if="!section.branches.length" class="task-rows__hint">
      {{ t('tasks.task.list.group_empty') }}
    </p>

    <div
      v-for="node in section.branches"
      :key="node.task.code"
      class="task-drag task-branch"
      :data-code="node.task.code"
    >
      <TaskRow
        :task="node.task"
        :depth="0"
        :last="true"
        :child-count="props.childCounts.get(node.task.code) ?? 0"
        :open="node.task.code === props.openCode"
        :reorderable="props.reorderable"
        :can-up="canStep(node.task.code, -1)"
        :can-down="canStep(node.task.code, 1)"
        :foldable="node.children.length > 0"
        @open="emit('open', $event)"
        @edit="emit('edit', $event)"
        @add-child="emit('addChild', $event)"
        @remove="emit('remove', $event)"
        @restore="emit('restore', $event)"
        @step="step(node.task.code, $event)"
      />

      <TaskSubtree
        v-if="node.children.length && !store.isCollapsed(node.task.code)"
        :nodes="node.children"
        :parent-code="node.task.code"
        :child-counts="props.childCounts"
        :open-code="props.openCode"
        :reorderable="props.reorderable"
        @open="emit('open', $event)"
        @edit="emit('edit', $event)"
        @add-child="emit('addChild', $event)"
        @remove="emit('remove', $event)"
        @restore="emit('restore', $event)"
        @move="fromSubtree"
      />
    </div>
  </div>
</template>

<style scoped>
/* ── Empty section ─────────────────────────────────────────────────────────────
   The height is set here, not by the caption inside: the caption goes away as soon as something
   is put into the group, and a drop target must be large enough to hit by hand. */
.task-rows--empty {
  display: flex;
  align-items: center;
  min-height: 44px;
}

.task-rows__hint {
  margin: 0;
  padding: 0 12px;
  font-size: 12px;
  line-height: 16px;
  color: var(--text-faint);
}

/* ── Branch ────────────────────────────────────────────────────────────────────
   The wrapper exists for dragging: it has no look of its own, but it is what moves — together
   with all the rows inside. */
.task-branch + .task-branch { border-top: 1px solid var(--border-soft); }

/* Gesture states are shared by branches and subtasks: both move as a `.task-drag` wrapper, and the
   same gesture must look the same. */
:deep(.task-drag--ghost) {
  opacity: 0.4;
  background: var(--accent-soft);
}

:deep(.task-drag--ghost) .task-row { background: transparent; }

/* While a branch is held, its rows do not react to hover: a highlight under the cursor at that
   moment would mean "drop here", and a branch cannot be dropped into itself. */
:deep(.task-drag--chosen) .task-row:hover { background: transparent; }
</style>

<!-- Not `scoped`: with `fallbackOnBody` the preview is a clone appended straight to `<body>`, so no
     ancestor carries this component's scope attribute and a `:deep` rule never matched it. -->
<style>
/* The preview under the cursor, lifted by a shadow — "picked up". Opacity and transform are not
   set here: SortableJS writes both inline on the clone (0.8, and the translate that moves it). */
.task-drag--preview {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  box-shadow: 0 12px 32px rgba(0, 0, 0, 0.28);
  cursor: grabbing;
}
</style>
