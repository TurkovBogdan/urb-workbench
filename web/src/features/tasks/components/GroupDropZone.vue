<script setup lang="ts">
// The group card header as a drop target.
//
// Needed because a collapsed card — and empty ones arrive collapsed — renders no row of tasks at
// all, so there was nothing to drop a task into, even though an empty card is on screen precisely
// as a move target. Every card always has a header, so the header takes the drop.
//
// Its own sortable rather than part of the task row: the header ACCEPTS but does not give
// (`pull: false`), and has no order inside (`sort: false`). Where the task goes is decided not by
// the drop point but by markup: `data-drop="end"` and `data-after` — the code of the last task in
// the group's row, after which the dropped one lands. The drop is resolved by the gesture's source
// (`drag.ts::anchorAfterDrop`), like any other.
//
// On drop the library puts the dragged row INSIDE the header and then takes it back out itself
// (the receiver's `onAdd` and the source's `onRemove`). While the row is in there it is hidden by
// style and the header is highlighted — that is the "let go and it goes here" feedback.
import { ref } from 'vue'
import { useDraggable } from 'vue-draggable-plus'

const props = defineProps<{
  /** Group code; empty string — "No group". */
  group: string
  /** Code of the last top-level task of this group; `null` — the group is empty. */
  after: string | null
}>()

const zone = ref<HTMLElement | null>(null)

// An array for the library: a receiver must be given one so that on drop the row can be removed
// from its markup. Nobody needs the array itself — it is reset after every drop.
const sink = ref<string[]>([])

useDraggable(zone, sink, {
  group: { name: 'tasks', pull: false, put: true },
  sort: false,
  draggable: '.task-drag',
  onAdd: () => { sink.value = [] },
})
</script>

<template>
  <div
    ref="zone"
    class="group-drop"
    data-drop="end"
    :data-group="props.group"
    :data-after="props.after ?? ''"
  >
    <slot />
  </div>
</template>

<!-- Not `scoped`: both rules target a row of ANOTHER component (`.task-drag` from the task row),
     and the scope attribute on it would not match — while `:has` cannot be expressed through
     `:deep`. The name `group-drop` is unique in the app, so nothing leaks. -->
<style>
/* A row that slid into the header during the gesture is not shown and takes no space: otherwise
   the header would grow by its height right under the cursor, and the target would move out from
   under the hand.
   It is hidden exactly this way — taken out of flow and invisible — and NOT with `display: none`:
   an element hidden like that has a zero rectangle, SortableJS uses it to compute where to place
   the row in the next row container and gets zero — the row got stuck in the first header the
   cursor passed over and could no longer be dropped into a row below it. */
.group-drop {
  position: relative;
}

.group-drop > .task-drag {
  position: absolute;
  inset: 0 0 auto 0;
  visibility: hidden;
  pointer-events: none;
}

/* Instead, the header itself is highlighted: color from theme tokens, like other gesture states. */
.group-drop:has(> .task-drag) {
  background: var(--accent-soft);
  box-shadow: inset 0 0 0 1px var(--accent);
  border-radius: inherit;
}
</style>
