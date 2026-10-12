<script setup lang="ts">
// A codex row as a drop target: let a note go on it and the note goes to the end of the codex's
// top level.
//
// Needed because a codex with no notes — or a folded one — renders no row of notes at all, so there
// would be nothing to drop into, though carrying a note into another codex is exactly this
// gesture. Every codex always has its row, so the row takes the drop. The same idea as the group
// header of the task list (`features/tasks/components/GroupDropZone.vue`).
//
// Its own sortable rather than part of the tree: the row ACCEPTS but never gives (`pull: false`)
// and has no order inside (`sort: false`). Where the note goes is decided by markup — `data-drop`,
// `data-parent` and `data-after`, the last top-level note — and resolved by the gesture's source
// (`drag.ts::anchorAfterDrop`), like any other drop.
import { ref } from 'vue'
import { useDraggable } from 'vue-draggable-plus'

const props = defineProps<{
  /** The codex this row stands for. */
  codex: string
  /** Code of the codex's last top-level note; `null` — it has none. */
  after: string | null
  /** Whether the dragged note may land here — the tree's rules, asked before the drop is offered. */
  accepts: (parent: string, code: string) => boolean
}>()

const zone = ref<HTMLElement | null>(null)

// The library needs an array on a receiver to take the note out of its markup on drop; the array
// itself means nothing and is emptied after every drop.
const sink = ref<string[]>([])

useDraggable(zone, sink, {
  group: {
    name: 'codex-notes',
    pull: false,
    put: (_to, _from, dragged) => {
      const code = (dragged as HTMLElement).dataset.code
      return !!code && props.accepts(props.codex, code)
    },
  },
  sort: false,
  draggable: '.codex-tree__item--note',
  onAdd: () => { sink.value = [] },
})
</script>

<template>
  <div
    ref="zone"
    class="codex-drop"
    data-drop="end"
    :data-parent="props.codex"
    :data-after="props.after ?? ''"
  >
    <slot />
  </div>
</template>

<!-- Not `scoped`: the rules target a tree item of another component, and `:has` cannot go through
     `:deep`. The name `codex-drop` is unique in the app. -->
<style>
/* A note that slid into the row during the gesture is hidden and takes no space — otherwise the row
   grows under the cursor and the target runs away from the hand. Out of flow and invisible, NOT
   `display: none`: SortableJS measures it, and a zero rectangle sticks the note in the first row
   the cursor passed (the same trap as the task list's group header). */
.codex-drop {
  position: relative;
  border-radius: 6px;
  transition: background-color 350ms cubic-bezier(0.15, 1, 0.3, 1);
}

.codex-drop > .codex-tree__item--note {
  position: absolute;
  inset: 0 0 auto 0;
  visibility: hidden;
  pointer-events: none;
}

/* "Let go and it goes into this codex": the row lights up in the codex's own color (its tree item
   carries the vars), the app accent for a codex without one. */
.codex-drop:has(> .codex-tree__item--note) {
  background: var(--gc-fill, var(--accent-soft));
  box-shadow: inset 0 0 0 1px var(--gc-ink, var(--accent));
}
</style>
