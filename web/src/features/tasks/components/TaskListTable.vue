<script setup lang="ts">
// The "List" format: task rows split by zone headings, subtasks as branches under their parent.
//
// Anatomy: a card with rows and a pagination bar. The search and filter panel is a SEPARATE card
// above the list (the page assembles it): search and filters control what the list shows and
// belong not to it but to the screen as a whole.
//
// BRANCHES AND DRAGGING live in `TaskRows` — one component per group card: a sortable is created
// on a container, and there are as many containers as zones. What remains here is the card around
// them.
//
// THE MARKUP IS NOT A TABLE. The list no longer has columns: their header said nothing (there is
// no column sorting here), and an eight-column grid forced every field to keep its width and so to
// fill it with something — a dash, a word, a badge. Now a row reads left to right like a phrase:
// state, importance, title, auxiliary marks. Three zones rather than eight cells, and a mark the
// task does not have is simply absent.
//
// QUIETER THAN THE TITLE. In a tracker the eye finds a row by its title; everything else is marks,
// and they must be quieter than the text. Hence the rule for the whole file: only state and
// urgency carry color, the rest is a glyph and muted 12px. There are no colored words or tonal
// pills in the row at all: a badge saying "In testing" reads on a par with the title and steals
// the first glance from it.
//
// One task is one row of exactly 36px: a list is scanned top to bottom, and rows of uneven height
// have to be examined. So the row has no description or body — the task is opened for those.
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  IconArrowDown,
  IconArrowUp,
  IconCheck,
  IconCopy,
  IconDotsVertical,
  IconPencil,
  IconPlus,
  IconTrash,
} from '@tabler/icons-vue'

import CounterButton from '@/components/CounterButton.vue'
import IconSwatch from '@/components/IconSwatch.vue'
import TablePaginationBar from '@/components/TablePaginationBar.vue'
import { useClipboard } from '@/composables/useClipboard'

import GroupDropZone from './GroupDropZone.vue'
import TaskRows from './TaskRows.vue'
import { useTasksStore, type TaskSection } from '../stores/tasks.store'
import type { GroupListRow, TaskListRow } from '../api'

const props = defineProps<{
  /** Code of the task the person went to from the list: on return they see their row marked. */
  openCode?: string | null
}>()

const emit = defineEmits<{
  /** Open a task: the code goes out, not the row — the URL is built from it. */
  open: [code: string]
  create: []
  /** Create a task in this card's group; `null` — the "No group" card. */
  createIn: [group: string | null]
  addChild: [task: TaskListRow]
  /** Edit a group: there is one form dialog per page, and the page holds it, not the list. */
  editGroup: [group: GroupListRow]
  /** Delete a group: the dialog asks what becomes of its tasks, and the page holds it too. */
  removeGroup: [group: GroupListRow]
}>()

const { t } = useI18n()
const store = useTasksStore()
const { copy, isCopied } = useClipboard()

// How many tasks each parent has — counted from the list already received rather than asking the
// backend: the response holds ALL tasks of the workspace, and the same arithmetic behind
// `has_children` is free here. One count for the whole list: each group card has its own rows
// component, and recounting the same thing in each is pointless.
const childCounts = computed(() => {
  const counts = new Map<string, number>()
  for (const task of store.items) {
    if (!task.parent_code) continue
    counts.set(task.parent_code, (counts.get(task.parent_code) ?? 0) + 1)
  }
  return counts
})

const showEmpty = computed(() => !store.loading && store.total === 0)

// ── Collapse state ────────────────────────────────────────────────────────────
// The default depends on whether the card has work: an empty one arrives collapsed — it is on
// screen as a drag target, not as content. The person's explicit choice beats the default, and
// the store keeps it; here we only tell it which default applies to this section.

function collapsed(section: TaskSection): boolean {
  return store.isCollapsed(section.group?.code ?? null, !section.tasks.length)
}

function toggleFold(section: TaskSection) {
  store.toggleCollapsed(section.group?.code ?? null, !section.tasks.length)
}

/**
 * Order is changed only on the FULL results.
 *
 * A narrowed list is a selection, not the layout: branches are not drawn in it, not all group
 * siblings are on screen, and "place after the visible neighbour" would mean something other than
 * what the person sees. Everything switches off at once — row dragging, the handles, and the
 * reorder items in the row and card menus.
 */
const reorderable = computed(() => !store.hasActiveFilters)

// ── Group reordering ──────────────────────────────────────────────────────────
// Only via card menu items, no gesture: a handle on every card and a second sortable on the page
// overloaded the list for an action done rarely (decision in `TASK@717492e127`).
//
// "Up" — land above the neighbour above, "Down" — below the neighbour below. Computed over the
// sections on screen, skipping "No group": it does not exist in the group layout.
//
// A step does not leave its block. Empty cards are shown below non-empty ones regardless of `sort`
// (see `sections` in the store), so "Down" on the last non-empty group would write a new order
// while changing nothing on screen — a step that looks broken. At the block boundary the menu item
// is disabled, which is more honest: there really is nowhere to move.

function blockOf(code: string): string[] {
  const own = store.sections.find((section) => section.group?.code === code)
  if (!own) return []
  const empty = !own.tasks.length
  return store.sections
    .filter((section) => !!section.group && !section.tasks.length === empty)
    .map((section) => section.group!.code)
}

function shiftTarget(code: string, direction: -1 | 1): string | undefined {
  const order = blockOf(code)
  const at = order.indexOf(code)
  if (at === -1) return undefined
  const target = at + direction
  if (target < 0 || target >= order.length) return undefined
  return order[target]
}

function canShift(code: string, direction: -1 | 1): boolean {
  return shiftTarget(code, direction) !== undefined
}

function shift(code: string, direction: -1 | 1) {
  const target = shiftTarget(code, direction)
  if (!target) return
  void store.reorderGroup(code, direction === -1 ? { before: target } : { after: target })
}

/**
 * A row was reordered — the store runs the reorder: it also re-reads the list after the response.
 *
 * Group and parent are passed on ONLY if named: an absent key means "leave as is", and losing that
 * distinction here would clear the group on an ordinary reorder.
 */
async function move(payload: {
  code: string
  after: string | null
  group?: string | null
  parent?: string | null
}) {
  await store.reorder(payload.code, payload.after, {
    ...('group' in payload ? { group: payload.group } : {}),
    ...('parent' in payload ? { parent: payload.parent } : {}),
  })
}

function onPageChange(page: number) {
  store.page = page
}

function onPageSizeChange(size: number) {
  store.pageSize = size
  store.resetPage()
}
</script>

<template>
  <div class="task-list">
    <!-- Refreshing a list already shown is a bar on top: replacing rows with a spinner would take
         off screen what the person is reading at that moment. -->
    <VProgressLinear v-if="store.loading && store.total > 0" indeterminate height="2" class="task-list__progress" />

    <VCard v-if="store.loading && !store.total" variant="outlined" rounded="lg">
      <div class="task-list__state">
        <VProgressCircular indeterminate size="24" width="3" />
      </div>
    </VCard>

    <!-- Empty for two different reasons with different answers: no tasks at all — invite creating
         the first; the filters found nothing — offer to clear them. -->
    <VCard v-else-if="showEmpty" variant="outlined" rounded="lg">
      <div class="task-list__state">
        <template v-if="store.isFilteredOut">
          <p class="task-list__state-title">{{ t('tasks.task.list.nothing_found') }}</p>
          <!-- The way out of empty results must change something. If no filters are applied and
               the default hid everything, "reset filters" would restore that very default — only
               lifting it helps here. -->
          <VBtn v-if="store.hasActiveFilters" variant="text" size="small" @click="store.clearFilters">
            {{ t('tasks.task.list.clear_filters') }}
          </VBtn>
          <VBtn v-else variant="text" size="small" @click="store.showFinished">
            {{ t('tasks.task.list.show_finished') }}
          </VBtn>
        </template>
        <template v-else>
          <p class="task-list__state-title">{{ t('tasks.task.list.empty') }}</p>
          <p class="task-list__state-hint">{{ t('tasks.task.list.empty_hint') }}</p>
          <VBtn color="primary" variant="flat" size="small" @click="emit('create')">
            <template #prepend><IconPlus :size="16" /></template>
            {{ t('tasks.task.list.add') }}
          </VBtn>
        </template>
      </div>
    </VCard>

    <!-- Group = card. Sections come WITHOUT `v-else`: on an empty page there are simply none (see
         the store), and tying them into a branch with the two states would keep the same answer
         in two places.
         Empty cards sit at the bottom and are muted: they are here as move targets, not content —
         a task is dragged into another group, and a group not on screen does not exist for the
         gesture. -->
    <VCard
      v-for="section in store.sections"
      :key="section.group?.code ?? 'no-group'"
      variant="outlined"
      rounded="lg"
      class="task-group"
      :class="{ 'task-group--empty': !section.tasks.length }"
    >
      <!-- The group header is the stock card anatomy (`VCardItem`): the sign in `#prepend`, the
           name as title, the description as subtitle. It handles aligning the sign with two lines
           of text and the spacing itself; custom markup would only approximate it.
           The sign is taken from the group card on its own page: the same thing must be
           recognisable in both lists. "No group" has no sign — a neutral dot instead: it is not a
           topic on a par with the others but the unsorted remainder.
           The header is also a drop target (`GroupDropZone`): a collapsed or empty card has no
           row of tasks, and a task dropped on the header is taken to the end of the group's
           row. -->
      <GroupDropZone
        :group="section.group?.code ?? ''"
        :after="store.lastRootOf(section.group?.code ?? null)"
      >
      <VCardItem class="task-group__head">
        <template #prepend>
          <IconSwatch
            v-if="section.group"
            :icon="section.group.icon"
            :color="section.group.color"
            :width="28"
          />
          <span v-else class="task-group__dot" />
        </template>

        <!-- Right after the name — the task count and the collapse arrow, the same button as on a
             task row with subtasks. No icon: the row's "subtasks" one would make the group read as
             a task with subtasks. Zero is shown: for a group it is an answer, not a missing
             count. -->
        <VCardTitle class="task-group__title">
          {{ section.group ? section.group.title : t('tasks.task.list.no_group') }}
          <CounterButton
            class="task-group__fold"
            :count="section.tasks.length"
            :folded="collapsed(section)"
            :label="t(collapsed(section) ? 'tasks.task.list.expand_group' : 'tasks.task.list.collapse_group')"
            @toggle="toggleFold(section)"
          />
        </VCardTitle>
        <VCardSubtitle v-if="section.group?.description">{{ section.group.description }}</VCardSubtitle>

        <!-- "No group" has no menu: there is no database row behind it, nothing to edit or move.
             The code is how the group is named to the agent, so copying it is at hand rather than
             only in the menu — the same button as on the groups page. -->
        <template #append>
          <VBtn
            v-if="section.group"
            variant="text"
            size="x-small"
            icon
            class="task-group__more"
            :aria-label="t('common.action.copy_code')"
            :title="t('common.action.copy_code')"
            @click="copy(section.group.code)"
          >
            <IconCheck v-if="isCopied(section.group.code)" :size="16" :stroke-width="1.7" />
            <IconCopy v-else :size="16" :stroke-width="1.7" />
          </VBtn>
          <VMenu v-if="section.group" location="bottom end">
            <template #activator="{ props: menu }">
              <VBtn
                v-bind="menu"
                variant="text"
                size="x-small"
                icon
                class="task-group__more"
                :aria-label="t('tasks.group.card.actions')"
              >
                <IconDotsVertical :size="16" :stroke-width="1.7" />
              </VBtn>
            </template>

            <VList density="compact" class="task-group__menu">
              <VListItem :prepend-icon="IconCopy" @click="copy(section.group.code)">
                <VListItemTitle>{{ t('common.action.copy_code') }}</VListItemTitle>
              </VListItem>
              <VListItem :prepend-icon="IconPencil" @click="emit('editGroup', section.group)">
                <VListItemTitle>{{ t('tasks.group.card.edit') }}</VListItemTitle>
              </VListItem>
              <VListItem :prepend-icon="IconPlus" @click="emit('createIn', section.group.code)">
                <VListItemTitle>{{ t('tasks.task.list.add_to_group') }}</VListItemTitle>
              </VListItem>

              <!-- The same two moves without a mouse: WCAG 2.2 SC 2.5.7 asks for a single-pointer
                   alternative to a gesture, and a menu that opens from the keyboard covers
                   SC 2.1.1 too. On narrowed results they are absent — as is the gesture itself. -->
              <template v-if="reorderable">
                <VListItem
                  :prepend-icon="IconArrowUp"
                  :disabled="!canShift(section.group.code, -1)"
                  @click="shift(section.group.code, -1)"
                >
                  <VListItemTitle>{{ t('tasks.group.card.move_up') }}</VListItemTitle>
                </VListItem>
                <VListItem
                  :prepend-icon="IconArrowDown"
                  :disabled="!canShift(section.group.code, 1)"
                  @click="shift(section.group.code, 1)"
                >
                  <VListItemTitle>{{ t('tasks.group.card.move_down') }}</VListItemTitle>
                </VListItem>
              </template>

              <VListItem
                :prepend-icon="IconTrash"
                class="task-group__menu-danger"
                @click="emit('removeGroup', section.group)"
              >
                <VListItemTitle>{{ t('tasks.group.card.delete') }}</VListItemTitle>
              </VListItem>
            </VList>
          </VMenu>
        </template>
      </VCardItem>
      </GroupDropZone>

      <template v-if="!collapsed(section)">
        <VDivider />

        <TaskRows
          :section="section"
          :open-code="props.openCode"
          :child-counts="childCounts"
          :reorderable="reorderable"
          @open="emit('open', $event)"
          @add-child="emit('addChild', $event)"
          @remove="store.remove($event)"
          @restore="store.restore($event)"
          @status="store.setStatus($event.code, $event.status)"
          @move="move"
        />
      </template>

      <!-- Adding stays under the card whether it is collapsed or not: a task is added to a group
           without unfolding everything already in it. -->
      <VDivider />
      <div class="task-group__foot">
        <VBtn variant="text" size="small" @click="emit('createIn', section.group?.code ?? null)">
          <template #prepend><IconPlus :size="16" :stroke-width="1.6" /></template>
          {{ t('tasks.task.list.add_to_group') }}
        </VBtn>
      </div>
    </VCard>

    <!-- The pagination bar is shared by all group cards and so sits below them, not inside any one:
         the whole list is paged, not a single group. It is shown only when there is more than one
         page: on a list of five tasks, "1–5 of 5" and a page-size picker are a caption under
         something that is entirely on screen anyway. -->
    <VCard v-if="store.pageCount > 1" variant="outlined" rounded="lg">
      <TablePaginationBar
        :page="store.page"
        :page-size="store.pageSize"
        :total="store.total"
        :page-count="store.pageCount"
        @update:page="onPageChange"
        @update:page-size="onPageSizeChange"
      />
    </VCard>
  </div>
</template>

<style scoped>
/* ── Group card ────────────────────────────────────────────────────────────────
   A group is its own card, not a heading in the middle of a shared canvas: it has a name, a sign
   and a subject, and all of that belongs to its tasks, not to the list as a whole. The gap between
   cards is larger than any inner one: it is what separates the groups. */
.task-list {
  position: relative;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

/* The progress bar lies OVER the cards and does not push them apart: as a row in the column, every
   re-request would jolt the whole list two pixels down. */
.task-list__progress {
  position: absolute;
  top: -6px;
  z-index: 1;
}

/* A group without tasks is a move target, not content: it is visible but must not compete for
   attention with groups that have work. The muting lifts under the cursor: a pointer over the card
   is already intent, and at that moment it stops being background. It is dimmed by opacity as a
   whole, not by color piece by piece: that way no header element falls out of the common tone. */
.task-group--empty {
  opacity: 0.5;
  transition: opacity 120ms ease;
}

.task-group--empty:hover {
  opacity: 1;
}

/* Header padding is tighter than vanilla: `VCardItem` is designed for a page-like card, while here
   it sits above a dense list of 36px rows. */
.task-group__head {
  padding: 10px 12px;
}

/* "No group" is not a color but its absence: a neutral dot instead of a sign, otherwise the
   remainder would look like a named group just like its neighbours. The box is the same as the
   sign's — headers of adjacent cards line up. */
.task-group__dot {
  width: 28px;
  flex: none;
  position: relative;
}

.task-group__dot::before {
  content: '';
  position: absolute;
  top: 50%;
  left: 50%;
  width: 6px;
  height: 6px;
  margin: -3px 0 0 -3px;
  border-radius: 50%;
  background: var(--text-faint);
}

/* Own font size and weight: vanilla `VCardTitle` is set for a page-like card title, while this is
   a group name above a list. The branch button sits on the same line, hence the line is flex. */
.task-group__title {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 0;
  font-size: 13px;
  font-weight: 600;
  line-height: 18px;
  color: var(--text);
}

/* The branch button's look is its own (`CounterButton`); the header sets only its place: a
   negative margin hides the button's padding, so the icon sits as far from the name as on a task
   row. Hovering the card reveals the button — but the variable is set on the header, not the whole
   card: otherwise it would leak into the task rows, and their buttons would show under the cursor
   too. */
.task-group__fold { margin-inline-start: -4px; }

.task-group:hover .task-group__head { --counter-button-color: var(--text-muted); }

/* The menu is always muted and shows under the cursor: it has no reason to draw attention. */
.task-group__more {
  color: var(--text-faint);
  opacity: 0.7;
  transition: opacity 120ms ease, color 120ms ease;
}

.task-group:hover .task-group__more {
  opacity: 1;
  color: var(--text-muted);
}

/* As on the groups page: deleting is the one item that costs something, and it says so in color. */
.task-group__menu-danger :deep(.v-list-item-title),
.task-group__menu-danger :deep(.v-list-item__prepend) { color: var(--error); }

.task-group__head :deep(.v-card-item__append) {
  display: flex;
  align-items: center;
}

/* The group description is one line under the name and quieter than it: a caption for the card,
   not text to read. A long one is cut, not wrapped: group headers must be the same height. */
.task-group__head :deep(.v-card-subtitle) {
  padding: 0;
  margin-top: 2px;
  font-size: 12px;
  line-height: 16px;
  color: var(--text-muted);
  opacity: 1;
}

/* The card's footer is a place, not a control: it does not react to the pointer, only the button in
   it does. The button's plus sits where a task's state glyph would. */
.task-group__foot {
  display: flex;
  align-items: center;
  height: 36px;
  padding-inline-start: 24px;
}

/* Set like a task title, not like a toolbar button: the footer continues the column of rows, and a
   heavier label would read louder than the tasks above it. */
.task-group__foot :deep(.v-btn) {
  font-size: 13px;
  font-weight: 400;
  color: var(--text-muted);
}

.task-list__state {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
  padding: 32px 16px;
  text-align: center;
}

.task-list__state-title {
  margin: 0;
  font-size: 14px;
  font-weight: 600;
  color: var(--text);
}

.task-list__state-hint {
  margin: 0 0 6px;
  font-size: 13px;
  color: var(--text-muted);
}
</style>
