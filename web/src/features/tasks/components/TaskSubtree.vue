<script setup lang="ts">
// The container of ONE parent's children and dragging within it.
//
// A separate, recursive component — for the same reason root rows live in `TaskRows`: a sortable
// is created ON A CONTAINER, and there are as many containers as parents with children. While the
// branch was drawn as a flat list of rows there was no such container at all, so there was nothing
// to reorder a subtask among its siblings with.
//
// THE GESTURE RULES ARE EXPRESSED BY THE SORTABLE GROUP, not by checks in the handler.
// `put: false` — nothing can be dropped into a branch from outside: neither a root task (it must
// not become a subtask by dragging) nor a subtask from another branch (changing the parent is
// moving a branch, a separate conversation). Reordering among ITS OWN siblings does not consult
// `put` and works.
//
// `pull: true` is kept, though: pulling a subtask up into a group card's container is allowed —
// that is detaching. The receiving side (`TaskRows`) decides whether to take it.
import { ref, watch } from 'vue'
import { useDraggable } from 'vue-draggable-plus'

import TaskRow from './TaskRow.vue'
import { anchorAfterDrop } from '../drag'
import { useTasksStore, type TaskNode } from '../stores/tasks.store'
import type { TaskListRow } from '../api'

/** Duration of the sibling reorder animation — the library's stock FLIP, same as for root rows. */
const ANIMATION_MS = 150

const props = defineProps<{
  /** Children of one parent, as nodes: each with its own children, depth and place in the row. */
  nodes: TaskNode[]
  /** Parent code: the container is tagged with it so the handler knows where the row came from. */
  parentCode: string
  childCounts: Map<string, number>
  openCode?: string | null
  reorderable?: boolean
}>()

const emit = defineEmits<{
  open: [code: string]
  addChild: [task: TaskListRow]
  remove: [code: string]
  restore: [code: string]
  status: [change: { code: string; status: string }]
  /**
   * The row moved: its place among siblings, and on detaching also `parent: null` with the group
   * of the card it was dropped into. Only the gesture knows the group; the menu item does not name
   * it, and the card fills it in.
   */
  move: [payload: {
    code: string
    after: string | null
    parent?: string | null
    group?: string | null
  }]
}>()

// Whether the branch under a row is collapsed — see the same store in `TaskRows`.
const store = useTasksStore()

const container = ref<HTMLElement | null>(null)

// The list the library itself moves around. We render not it but `nodes` from the store — that
// stays the source of truth, and this array exists for sortable to keep its own state.
const codes = ref<string[]>([])

watch(
  () => props.nodes,
  (nodes) => { codes.value = nodes.map((node) => node.task.code) },
  { immediate: true },
)

const sortable = useDraggable(container, codes, {
  group: { name: 'tasks', pull: true, put: false },
  handle: '.drag-handle',
  draggable: '.task-drag',
  // A handle from a NESTED container belongs to it, not to us (see the same filter in `TaskRows`).
  filter: (event: Event) =>
    (event.target as HTMLElement | null)?.closest('.task-subtree, .task-rows') !== container.value,
  animation: ANIMATION_MS,
  // Pointer Events instead of native DnD — for the same reasons as with root rows.
  forceFallback: true,
  fallbackOnBody: true,
  ghostClass: 'task-drag--ghost',
  chosenClass: 'task-drag--chosen',
  dragClass: 'task-drag--drag',
  fallbackClass: 'task-drag--preview',
  fallbackTolerance: 4,
  scroll: true,
  scrollSensitivity: 80,
  onStart: () => { store.dragging = true },
  onEnd: (event) => {
    store.dragging = false
    const item = event.item as HTMLElement
    const code = item.dataset.code
    if (!code) return
    const to = event.to as HTMLElement
    const after = anchorAfterDrop(to, code, event.newIndex)

    // The SOURCE resolves the gesture, not the receiver: the library sends `onEnd` to the sortable
    // the drag started from — the receiver gets only `onAdd` and knows nothing of the source
    // branch. Hence the decision is made here: the subtask went into a root container (its markup
    // carries a group tag) — so it was pulled out of the branch, and that is a detach.
    if (to !== event.from) {
      if (to.dataset.group === undefined) return
      emit('move', { code, after, parent: null, group: to.dataset.group || null })
      return
    }

    if (event.oldIndex === event.newIndex) return
    emit('move', { code, after })
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
  const order = props.nodes.map((node) => node.task.code)
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
 * Detaching via the menu item. The item has no drop point, so the task goes to the TOP of its
 * group's row (`after: null`).
 *
 * To the top, not the end, although a fresh task is placed at the bottom: a detached task is not
 * fresh, it was just pulled out of a branch by hand — and the person should see the result rather
 * than hunt for the row at the tail of the card. The gesture does not face this question at all:
 * there the drop names the place.
 */
function detach(code: string): void {
  emit('move', { code, after: null, parent: null })
}
</script>

<template>
  <div ref="container" class="task-subtree" :data-parent="props.parentCode">
    <div
      v-for="node in props.nodes"
      :key="node.task.code"
      class="task-drag task-subtree__item"
      :data-code="node.task.code"
    >
      <TaskRow
        :task="node.task"
        :depth="node.depth"
        :last="node.last"
        :child-count="props.childCounts.get(node.task.code) ?? 0"
        :open="node.task.code === props.openCode"
        :reorderable="props.reorderable"
        :can-up="canStep(node.task.code, -1)"
        :can-down="canStep(node.task.code, 1)"
        :foldable="node.children.length > 0"
        @open="emit('open', $event)"
        @add-child="emit('addChild', $event)"
        @remove="emit('remove', $event)"
        @restore="emit('restore', $event)"
        @status="emit('status', $event)"
        @step="step(node.task.code, $event)"
        @detach="detach(node.task.code)"
      />

      <!-- Recursion: a child has children of its own, with their own container and sortable. -->
      <TaskSubtree
        v-if="node.children.length && !store.isCollapsed(node.task.code)"
        :nodes="node.children"
        :parent-code="node.task.code"
        :child-counts="props.childCounts"
        :open-code="props.openCode"
        :reorderable="props.reorderable"
        @open="emit('open', $event)"
        @add-child="emit('addChild', $event)"
        @remove="emit('remove', $event)"
        @restore="emit('restore', $event)"
        @status="emit('status', $event)"
        @move="emit('move', $event)"
      />
    </div>
  </div>
</template>

<style scoped>
/* The container has no look of its own: it exists for the gesture. Its height comes from the rows
   inside, and the dividers are drawn by the row itself. */
.task-subtree__item + .task-subtree__item,
.task-subtree > .task-subtree__item:first-child {
  border-top: 1px solid var(--border-soft);
}
</style>
