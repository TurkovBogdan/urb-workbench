<script lang="ts">
/** What a row needs from an entity: a workspace and a group both carry exactly this. */
export interface EntityRow {
  code: string
  title: string
  description: string
  /** A name from the `shared/colors.ts` registry; empty — the app accent. */
  color: string
  /** A name from the `shared/icons.ts` registry; empty — the fallback icon. */
  icon: string
  updated_at: string
  deleted_at: string | null
}

/** One number in the counters column, its label already translated and declined by the caller. */
export interface EntityRowCounter {
  key: string
  count: number
  label: string
}

/** The entity-specific words: the deleted mark agrees in gender, the handle names what it moves. */
export interface EntityRowLabels {
  drag: string
  deleted: string
  actions: string
  updatedAt: string
  edit: string
  delete: string
  restore: string
  purge: string
}
</script>

<script setup lang="ts" generic="T extends EntityRow">
// Entity rows, and the order they stand in — the workspaces page and the groups page.
//
// A separate component from the page for one reason, the same as `TaskRows` in the task list: a
// sortable is created on a container when it mounts, and on the page the list sits at the end of a
// `v-if` chain (loading, error, empty, nothing found) — it appears later than the page does. Here
// the container and the sortable are born and die together.
//
// DRAGGING follows the task list and the research behind it: Pointer Events instead of native
// DnD (`forceFallback` — touch, a styled preview, a managed cursor), the app's one `DragHandle`,
// and the position reported as an index for `useListReorder`, which turns it into a neighbour.
// The handle stands OUTSIDE the row, in the gutter to its left: the row itself is a click target
// (it opens the edit dialog), and a grip inside it would compete with that click for the same
// pixels.
import { ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useDraggable } from 'vue-draggable-plus'
import {
  IconCheck,
  IconCopy,
  IconDotsVertical,
  IconFlame,
  IconPencil,
  IconRestore,
  IconTrash,
} from '@tabler/icons-vue'

import DragHandle from '@/components/DragHandle.vue'
import { colorVarsByName } from '@/shared/colors'
import { iconByName } from '@/shared/icons'
import { fmtDateTime } from '@/shared/utils/date'
import { useClipboard } from '@/composables/useClipboard'

const props = defineProps<{
  items: T[]
  /** A narrowed or trash-mixed list cannot be reordered: a drop there names no real place. */
  reorderable: boolean
  counters: (item: T) => EntityRowCounter[]
  labels: EntityRowLabels
}>()

const emit = defineEmits<{
  edit: [item: T]
  remove: [item: T]
  restore: [item: T]
  purge: [item: T]
  move: [code: string, toIndex: number]
}>()

const { t } = useI18n()
const { copy, isCopied } = useClipboard()

/** The task list's move duration: one gesture must feel the same on every page. */
const ANIMATION_MS = 150

const container = ref<HTMLElement | null>(null)

// The array the library moves around. We render `items`, not this: the caller's store stays the
// source of truth, and this copy exists only for sortable to keep its own state.
const codes = ref<string[]>([])

watch(
  () => props.items,
  (rows) => { codes.value = rows.map((item) => item.code) },
  { immediate: true },
)

const sortable = useDraggable(container, codes, {
  handle: '.drag-handle',
  draggable: '.entity-item',
  animation: ANIMATION_MS,
  forceFallback: true,
  fallbackOnBody: true,
  ghostClass: 'entity-drag--ghost',
  chosenClass: 'entity-drag--chosen',
  fallbackClass: 'entity-drag--preview',
  // Grab threshold: a short twitch on the handle stays a click rather than starting a move.
  fallbackTolerance: 4,
  scroll: true,
  scrollSensitivity: 80,
  onEnd: (event) => {
    const code = (event.item as HTMLElement).dataset.code
    // Lifted and put back where it was: no request — "after the neighbour above" for an untouched
    // row would be a reorder nobody asked for.
    if (!code || event.newIndex === undefined || event.oldIndex === event.newIndex) return
    emit('move', code, event.newIndex)
  },
})

// When the list cannot be reordered the gesture is switched off and the handles are not drawn —
// a grip that does nothing would lie.
watch(
  () => props.reorderable,
  (on) => { if (on) sortable.resume(); else sortable.pause() },
  { immediate: true },
)
</script>

<template>
  <!-- One entity — one full-width line: what it is | how much is inside | when it was touched and
       what can be done with it. The columns after the name have fixed widths, so the vertical
       dividers stand one under another and the numbers read down as a column. -->
  <div ref="container" class="entity-list">
    <!-- The wrapper is what moves: the row together with its handle in the gutter. `drag-row`
         is the hook `DragHandle` shows itself on when the pointer is anywhere over the line. -->
    <div
      v-for="item in items"
      :key="item.code"
      class="entity-item drag-row"
      :data-code="item.code"
    >
      <DragHandle
        v-if="reorderable && !item.deleted_at"
        :label="labels.drag"
        class="entity-item__handle"
      />

      <!-- The entity colour lives on the row itself: the icon badge is painted from it. A live row
           opens its edit dialog — the same one as the menu item. A deleted one cannot be edited
           (409), so it is not clickable at all: it has no handler, and Vuetify does not render it
           as a link. -->
      <VCard
        variant="flat"
        class="entity-row color-tones"
        :class="{ 'entity-row--deleted': item.deleted_at }"
        :style="colorVarsByName(item.color)"
        v-on="item.deleted_at ? {} : { click: () => emit('edit', item) }"
      >
        <span class="entity-row__icon">
          <component :is="iconByName(item.icon)" :size="20" :stroke-width="1.6" />
        </span>

        <div class="entity-row__main">
          <div class="entity-row__head">
            <h3 class="entity-row__title">{{ item.title }}</h3>
            <!-- The deleted mark sits next to the name: it changes the meaning of the whole line,
                 and must be noticed before reaching the counters. -->
            <VChip v-if="item.deleted_at" color="error" variant="tonal" size="x-small">
              {{ labels.deleted }}
            </VChip>
          </div>
          <p v-if="item.description" class="entity-row__desc">{{ item.description }}</p>
        </div>

        <VDivider vertical class="entity-row__divider" />

        <!-- The caller decides what is counted. With no counters at all the column stays empty
             and keeps its width, so the dividers still line up. -->
        <div class="entity-row__counts">
          <span v-for="counter in counters(item)" :key="counter.key" class="entity-row__counter">
            <span class="entity-row__count">{{ counter.count }}</span>
            <span class="entity-row__count-label">{{ counter.label }}</span>
          </span>
        </div>

        <VDivider vertical class="entity-row__divider" />

        <span class="entity-row__updated">
          {{ fmtDateTime(item.updated_at) }}
          <VTooltip activator="parent" location="top">
            {{ labels.updatedAt }}
          </VTooltip>
        </span>

        <div class="entity-row__actions">
          <!-- The code is how the entity is named to the agent, so copying is at hand, not only in
               the menu. `.stop` — copying must not also open the row's edit. -->
          <VBtn
            icon
            variant="text"
            class="entity-row__action"
            :title="t('common.action.copy_code')"
            @click.stop="copy(item.code)"
          >
            <IconCheck v-if="isCopied(item.code)" :size="16" :stroke-width="1.6" />
            <IconCopy v-else :size="16" :stroke-width="1.6" />
          </VBtn>

          <VMenu location="bottom end" :offset="4">
            <template #activator="{ props: menu }">
              <VBtn
                v-bind="menu"
                icon
                variant="text"
                class="entity-row__action"
                :title="labels.actions"
                @click.stop
              >
                <IconDotsVertical :size="16" :stroke-width="1.6" />
              </VBtn>
            </template>

            <!-- The action set depends on the state: a live one gets edit and soft delete, a
                 deleted one gets restore and purge. The backend refuses to edit a deleted one
                 (409), and showing an item that is bound to fail means lying with a button. -->
            <VList density="compact">
              <!-- Copying the code does not depend on state: a deleted entity keeps its code. -->
              <VListItem :prepend-icon="IconCopy" @click="copy(item.code)">
                <VListItemTitle>{{ t('common.action.copy_code') }}</VListItemTitle>
              </VListItem>
              <template v-if="!item.deleted_at">
                <VListItem :prepend-icon="IconPencil" @click="emit('edit', item)">
                  <VListItemTitle>{{ labels.edit }}</VListItemTitle>
                </VListItem>
                <VListItem
                  :prepend-icon="IconTrash"
                  class="entity-row__menu-danger"
                  @click="emit('remove', item)"
                >
                  <VListItemTitle>{{ labels.delete }}</VListItemTitle>
                </VListItem>
              </template>
              <template v-else>
                <VListItem :prepend-icon="IconRestore" @click="emit('restore', item)">
                  <VListItemTitle>{{ labels.restore }}</VListItemTitle>
                </VListItem>
                <VListItem
                  :prepend-icon="IconFlame"
                  class="entity-row__menu-danger"
                  @click="emit('purge', item)"
                >
                  <VListItemTitle>{{ labels.purge }}</VListItemTitle>
                </VListItem>
              </template>
            </VList>
          </VMenu>
        </div>
      </VCard>
    </div>
  </div>
</template>

<style scoped>
.entity-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

/* The wrapper is the drag item; the handle hangs in the gutter to the left of the row, centred on
   it, outside its border. */
.entity-item { position: relative; }

.entity-item__handle {
  position: absolute;
  top: 50%;
  left: -22px;
  transform: translateY(-50%);
}

.entity-row {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 14px 16px;
}

/* A deleted one is muted entirely, not just tagged with a label: a line in the trash must not
   compete for attention with live ones. Hover restores the opacity — so it can be read without
   restoring it. */
.entity-row--deleted {
  opacity: 0.55;
}

.entity-row--deleted:hover {
  opacity: 1;
}

.entity-row__icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 34px;
  height: 34px;
  border-radius: 8px;
  /* The entity colour, or else the app accent: the same fallback as for the icon. */
  color: var(--gc-ink, var(--accent));
  background: var(--gc-fill, var(--accent-soft));
  flex: none;
}

/* Name and description take whatever the fixed columns leave; each is one line, cut with an
   ellipsis — the full description is one click away, in the edit dialog. The block keeps the
   height of both lines even without a description, so every row is the same height and a lone
   name sits centred. */
.entity-row__main {
  flex: 1;
  min-width: 0;
  min-height: 38px;
  display: flex;
  flex-direction: column;
  justify-content: center;
  gap: 2px;
}

.entity-row__head {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.entity-row__title {
  font-size: 14px;
  font-weight: 600;
  color: var(--text);
  margin: 0;
  line-height: 1.35;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.entity-row__desc {
  font-size: 12px;
  color: var(--text-muted);
  line-height: 1.45;
  margin: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* The divider spans the text block's height, not the row's: full height would cut the row into
   boxes, a shorter rule only separates the columns. */
.entity-row__divider {
  align-self: center;
  height: 28px;
  opacity: 1;
  border-color: var(--border);
}

/* Fixed widths: the dividers on neighbouring lines stand one under another, and the numbers of
   every row read down as a column. */
.entity-row__counts {
  flex: none;
  width: 168px;
  display: flex;
  align-items: baseline;
  gap: 8px;
}

/* Each counter has its own width: the second one starts at the same place whether the first
   number has one digit or three. */
.entity-row__counter {
  display: inline-flex;
  align-items: baseline;
  gap: 6px;
  min-width: 76px;
}

.entity-row__count {
  font-family: var(--font-mono);
  font-size: 16px;
  font-weight: 600;
  color: var(--text);
  line-height: 1;
}

.entity-row__count-label {
  font-size: 11px;
  font-weight: 500;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--text-muted);
}

.entity-row__updated {
  flex: none;
  width: 104px;
  font-size: 11px;
  color: var(--text-faint);
  white-space: nowrap;
}

.entity-row__actions {
  flex: none;
  display: flex;
  align-items: center;
  gap: 2px;
}

/* The box is set here, not via the `size`/`density` props: for an icon button Vuetify computes
   the side as `--v-btn-height + 12px`, and density only changes the height. An unlayered rule
   overrides `@layer vuetify-components` (see docs/frontend/vuetify-css-patterns). */
.entity-row__action {
  width: 26px;
  min-width: 26px;
  height: 26px;
  color: var(--text-faint);
}

.entity-row__action:hover { color: var(--text); }

.entity-row__menu-danger :deep(.v-list-item-title) { color: var(--error); }
.entity-row__menu-danger :deep(.v-list-item__prepend) { color: var(--error); }

/* The place the row will land: its own outline, tinted — "it goes here". The handle is hidden on
   it, there is nothing to grab on a placeholder. */
.entity-drag--ghost .entity-row {
  opacity: 0.4;
  background: var(--accent-soft);
}

.entity-drag--ghost .entity-item__handle { visibility: hidden; }
</style>

<!-- Not `scoped`: with `fallbackOnBody` the preview is a clone appended straight to `<body>`, the
     same reason as in `TaskRows`. -->
<style>
/* The preview under the cursor, lifted by a shadow — "picked up". Opacity and transform are not
   set here: SortableJS writes both inline on the clone. */
.entity-drag--preview .entity-row {
  box-shadow: 0 12px 32px rgba(0, 0, 0, 0.28);
  cursor: grabbing;
}

.entity-drag--preview .entity-item__handle { visibility: hidden; }
</style>
