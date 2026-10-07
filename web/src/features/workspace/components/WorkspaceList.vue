<script setup lang="ts">
// The workspace rows, and the order they stand in.
//
// A separate component from the page for one reason, the same as `TaskRows` in the task list: a
// sortable is created on a container when it mounts, and on the page the list sits at the end of a
// `v-if` chain (loading, error, empty, nothing found) — it appears later than the page does. Here
// the container and the sortable are born and die together.
//
// DRAGGING follows the task list and the research behind it: Pointer Events instead of native
// DnD (`forceFallback` — touch, a styled preview, a managed cursor), the app's one `DragHandle`,
// and the position sent as a neighbour, never as a `sort` number. The handle stands OUTSIDE the
// row, in the gutter to its left: the row itself is a click target (it opens the edit dialog),
// and a grip inside it would compete with that click for the same pixels.
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

import { useWorkspacesStore } from '../stores/workspaces.store'
import type { WorkspaceListRow } from '../api'

const emit = defineEmits<{
  edit: [workspace: WorkspaceListRow]
  remove: [workspace: WorkspaceListRow]
  purge: [workspace: WorkspaceListRow]
}>()

const { t } = useI18n()
const store = useWorkspacesStore()
const { copy, isCopied } = useClipboard()

/** The task list's move duration: one gesture must feel the same on both pages. */
const ANIMATION_MS = 150

const container = ref<HTMLElement | null>(null)

// The array the library moves around. We render `store.visible`, not this: the store stays the
// source of truth, and this copy exists only for sortable to keep its own state.
const codes = ref<string[]>([])

watch(
  () => store.visible,
  (rows) => { codes.value = rows.map((workspace) => workspace.code) },
  { immediate: true },
)

const sortable = useDraggable(container, codes, {
  handle: '.drag-handle',
  draggable: '.workspace-item',
  animation: ANIMATION_MS,
  forceFallback: true,
  fallbackOnBody: true,
  ghostClass: 'workspace-drag--ghost',
  chosenClass: 'workspace-drag--chosen',
  fallbackClass: 'workspace-drag--preview',
  // Grab threshold: a short twitch on the handle stays a click rather than starting a move.
  fallbackTolerance: 4,
  scroll: true,
  scrollSensitivity: 80,
  onEnd: (event) => {
    const code = (event.item as HTMLElement).dataset.code
    // Lifted and put back where it was: no request — "after the neighbour above" for an untouched
    // row would be a reorder nobody asked for.
    if (!code || event.newIndex === undefined || event.oldIndex === event.newIndex) return
    store.move(code, event.newIndex)
  },
})

// Narrowed or mixed with the trash, the list cannot be reordered (see `store.reorderable`): the
// gesture is switched off and the handles are not drawn — a grip that does nothing would lie.
watch(
  () => store.reorderable,
  (on) => { if (on) sortable.resume(); else sortable.pause() },
  { immediate: true },
)
</script>

<template>
  <!-- One workspace — one full-width line: what it is | how much is inside | when it was touched
       and what can be done with it. The columns after the name have fixed widths, so the
       vertical dividers stand one under another and the numbers read down as a column. -->
  <div ref="container" class="workspace-list">
    <!-- The wrapper is what moves: the row together with its handle in the gutter. `drag-row`
         is the hook `DragHandle` shows itself on when the pointer is anywhere over the line. -->
    <div
      v-for="workspace in store.visible"
      :key="workspace.code"
      class="workspace-item drag-row"
      :data-code="workspace.code"
    >
      <DragHandle
        v-if="store.reorderable && !workspace.deleted_at"
        :label="t('workspace.card.drag')"
        class="workspace-item__handle"
      />

      <!-- The workspace colour lives on the row itself: the icon badge is painted from it. A live
           row opens its edit dialog — the same one as the menu item. A deleted one cannot be
           edited (409), so it is not clickable at all: it has no handler, and Vuetify does not
           render it as a link. -->
      <VCard
        variant="flat"
        class="workspace-row color-tones"
        :class="{ 'workspace-row--deleted': workspace.deleted_at }"
        :style="colorVarsByName(workspace.color)"
        v-on="workspace.deleted_at ? {} : { click: () => emit('edit', workspace) }"
      >
        <span class="workspace-row__icon">
          <component :is="iconByName(workspace.icon)" :size="20" :stroke-width="1.6" />
        </span>

        <div class="workspace-row__main">
          <div class="workspace-row__head">
            <h3 class="workspace-row__title">{{ workspace.title }}</h3>
            <!-- The deleted mark sits next to the name: it changes the meaning of the whole line,
                 and must be noticed before reaching the counters. -->
            <VChip v-if="workspace.deleted_at" color="error" variant="tonal" size="x-small">
              {{ t('workspace.card.deleted') }}
            </VChip>
          </div>
          <p v-if="workspace.description" class="workspace-row__desc">{{ workspace.description }}</p>
        </div>

        <VDivider vertical class="workspace-row__divider" />

        <!-- The counters are not listed here: the modules on top define the set, and the row
             renders what arrived together with the label key. With none at all the column stays
             empty — a legitimate state for an install without application modules. -->
        <div class="workspace-row__counts">
          <span v-for="counter in workspace.counters" :key="counter.key" class="workspace-row__counter">
            <span class="workspace-row__count">{{ counter.count }}</span>
            <span class="workspace-row__count-label">{{ t(counter.label_key) }}</span>
          </span>
        </div>

        <VDivider vertical class="workspace-row__divider" />

        <span class="workspace-row__updated">
          {{ fmtDateTime(workspace.updated_at) }}
          <VTooltip activator="parent" location="top">
            {{ t('workspace.card.updated_at') }}
          </VTooltip>
        </span>

        <div class="workspace-row__actions">
          <!-- As on a group card: the code is how the workspace is named to the agent — in
               `workspace_use` and in MCP_WORKSPACE — so copying is at hand, not only in the menu.
               `.stop` — copying must not also open the row's edit. -->
          <VBtn
            icon
            variant="text"
            class="workspace-row__action"
            :title="t('common.action.copy_code')"
            @click.stop="copy(workspace.code)"
          >
            <IconCheck v-if="isCopied(workspace.code)" :size="16" :stroke-width="1.6" />
            <IconCopy v-else :size="16" :stroke-width="1.6" />
          </VBtn>

          <VMenu location="bottom end" :offset="4">
            <template #activator="{ props: menu }">
              <VBtn
                v-bind="menu"
                icon
                variant="text"
                class="workspace-row__action"
                :title="t('workspace.card.actions')"
                @click.stop
              >
                <IconDotsVertical :size="16" :stroke-width="1.6" />
              </VBtn>
            </template>

            <!-- The action set depends on the state: a live one gets edit and soft delete, a
                 deleted one gets restore and purge. The backend refuses to edit a deleted one
                 (409), and showing an item that is bound to fail means lying with a button. -->
            <VList density="compact">
              <!-- Copying the code does not depend on state: a deleted workspace keeps its code. -->
              <VListItem :prepend-icon="IconCopy" @click="copy(workspace.code)">
                <VListItemTitle>{{ t('common.action.copy_code') }}</VListItemTitle>
              </VListItem>
              <template v-if="!workspace.deleted_at">
                <VListItem :prepend-icon="IconPencil" @click="emit('edit', workspace)">
                  <VListItemTitle>{{ t('workspace.card.edit') }}</VListItemTitle>
                </VListItem>
                <VListItem
                  :prepend-icon="IconTrash"
                  class="workspace-row__menu-danger"
                  @click="emit('remove', workspace)"
                >
                  <VListItemTitle>{{ t('workspace.card.delete') }}</VListItemTitle>
                </VListItem>
              </template>
              <template v-else>
                <VListItem :prepend-icon="IconRestore" @click="store.restore(workspace.code)">
                  <VListItemTitle>{{ t('workspace.card.restore') }}</VListItemTitle>
                </VListItem>
                <VListItem
                  :prepend-icon="IconFlame"
                  class="workspace-row__menu-danger"
                  @click="emit('purge', workspace)"
                >
                  <VListItemTitle>{{ t('workspace.card.purge') }}</VListItemTitle>
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
.workspace-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

/* The wrapper is the drag item; the handle hangs in the gutter to the left of the row, centred on
   it, outside its border. */
.workspace-item { position: relative; }

.workspace-item__handle {
  position: absolute;
  top: 50%;
  left: -22px;
  transform: translateY(-50%);
}

.workspace-row {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 14px 16px;
}

/* A deleted one is muted entirely, not just tagged with a label: a line in the trash must not
   compete for attention with live ones. Hover restores the opacity — so it can be read without
   restoring it. */
.workspace-row--deleted {
  opacity: 0.55;
}

.workspace-row--deleted:hover {
  opacity: 1;
}

.workspace-row__icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 34px;
  height: 34px;
  border-radius: 8px;
  /* The workspace colour, or else the app accent: the same fallback as for the icon. */
  color: var(--gc-ink, var(--accent));
  background: var(--gc-fill, var(--accent-soft));
  flex: none;
}

/* Name and description take whatever the fixed columns leave; each is one line, cut with an
   ellipsis — the full description is one click away, in the edit dialog. The block keeps the
   height of both lines even without a description, so every row is the same height and a lone
   name sits centred. */
.workspace-row__main {
  flex: 1;
  min-width: 0;
  min-height: 38px;
  display: flex;
  flex-direction: column;
  justify-content: center;
  gap: 2px;
}

.workspace-row__head {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.workspace-row__title {
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

.workspace-row__desc {
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
.workspace-row__divider {
  align-self: center;
  height: 28px;
  opacity: 1;
  border-color: var(--border);
}

/* Fixed widths: the dividers on neighbouring lines stand one under another, and the numbers of
   every workspace read down as a column. */
.workspace-row__counts {
  flex: none;
  width: 168px;
  display: flex;
  align-items: baseline;
  gap: 8px;
}

/* Each counter has its own width: the second one starts at the same place whether the first
   number has one digit or three. */
.workspace-row__counter {
  display: inline-flex;
  align-items: baseline;
  gap: 6px;
  min-width: 76px;
}

.workspace-row__count {
  font-family: var(--font-mono);
  font-size: 16px;
  font-weight: 600;
  color: var(--text);
  line-height: 1;
}

.workspace-row__count-label {
  font-size: 11px;
  font-weight: 500;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--text-muted);
}

.workspace-row__updated {
  flex: none;
  width: 104px;
  font-size: 11px;
  color: var(--text-faint);
  white-space: nowrap;
}

.workspace-row__actions {
  flex: none;
  display: flex;
  align-items: center;
  gap: 2px;
}

/* The box is set here, not via the `size`/`density` props: for an icon button Vuetify computes
   the side as `--v-btn-height + 12px`, and density only changes the height. An unlayered rule
   overrides `@layer vuetify-components` (see docs/frontend/vuetify-css-patterns). */
.workspace-row__action {
  width: 26px;
  min-width: 26px;
  height: 26px;
  color: var(--text-faint);
}

.workspace-row__action:hover { color: var(--text); }

.workspace-row__menu-danger :deep(.v-list-item-title) { color: var(--error); }
.workspace-row__menu-danger :deep(.v-list-item__prepend) { color: var(--error); }

/* The place the row will land: its own outline, tinted — "it goes here". The handle is hidden on
   it, there is nothing to grab on a placeholder. */
.workspace-drag--ghost .workspace-row {
  opacity: 0.4;
  background: var(--accent-soft);
}

.workspace-drag--ghost .workspace-item__handle { visibility: hidden; }
</style>

<!-- Not `scoped`: with `fallbackOnBody` the preview is a clone appended straight to `<body>`, the
     same reason as in `TaskRows`. -->
<style>
/* The preview under the cursor, lifted by a shadow — "picked up". Opacity and transform are not
   set here: SortableJS writes both inline on the clone. */
.workspace-drag--preview .workspace-row {
  box-shadow: 0 12px 32px rgba(0, 0, 0, 0.28);
  cursor: grabbing;
}

.workspace-drag--preview .workspace-item__handle { visibility: hidden; }
</style>
