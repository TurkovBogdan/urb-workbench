<script setup lang="ts">
// One task list row: state, importance, title, auxiliary marks, menu.
//
// A separate component because a branch has two kinds of rows — root and subtask — and they live
// in different containers: each container has its own sortable (see `TaskRows` and `TaskSubtree`).
// The row itself knows nothing about this: it is told what it can do, and it shows that.
//
// THE MARKUP IS NOT A TABLE. A row reads left to right like a phrase: state, importance, title,
// marks. A mark the task does not have is simply absent — instead of a dash in a cell.
//
// QUIETER THAN THE TITLE. In a tracker the eye finds a row by its title; everything else is marks,
// and they must be quieter than the text. Hence the rule for the whole file: only state and
// urgency carry color, the rest is a glyph and muted 12px. There are no colored words or tonal
// pills in the row at all: a badge saying "In testing" reads on a par with the title and steals
// the first glance from it.
//
// Exactly 36px: a list is scanned top to bottom, and rows of uneven height have to be examined.
// So there is no description or body here — the task is opened for those.
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  IconArrowDown,
  IconArrowUp,
  IconDotsVertical,
  IconPencil,
  IconRestore,
  IconSubtask,
  IconTrash,
  IconUnlink,
} from '@tabler/icons-vue'

import CounterButton from '@/components/CounterButton.vue'
import DragHandle from '@/components/DragHandle.vue'
import { fmtDate, fmtDateShort } from '@/shared/utils/date'

import { isTerminal, priorityColor, priorityIcon, statusColor, statusIcon } from '../labels'
import { useTasksStore } from '../stores/tasks.store'
import type { TaskListRow } from '../api'

const props = defineProps<{
  task: TaskListRow
  /** Zero — a branch root, then subtasks: depth drives the indent and the guide line. */
  depth: number
  /** Last among siblings — the guide line bends instead of running through. */
  last: boolean
  /** How many subtasks it has; zero — no mark. */
  childCount: number
  /** This is the task the person navigated to from the list. */
  open?: boolean
  /** The order in these results can be changed: show the handle and the reorder items. */
  reorderable?: boolean
  /** There is room to step up / down among siblings; the container computes it — it knows the row. */
  canUp?: boolean
  canDown?: boolean
  /**
   * A branch is drawn under the row and can be collapsed. The container decides: it knows whether
   * the task has visible children — on narrowed results there are no branches at all, nor arrows.
   */
  foldable?: boolean
}>()

const emit = defineEmits<{
  open: [code: string]
  edit: [task: TaskListRow]
  addChild: [task: TaskListRow]
  remove: [code: string]
  restore: [code: string]
  /** A step along the sibling row without a mouse. */
  step: [direction: -1 | 1]
  /** Detach from the parent: the subtask becomes a regular task. */
  detach: []
}>()

const { t } = useI18n()
const store = useTasksStore()

// Branch collapse state lives in the store next to group card collapse state — one map for both:
// task and group codes never collide. A task defaults to expanded.
const folded = computed(() => store.isCollapsed(props.task.code))

/** Work is closed or the task is in the trash — the row goes into a muted tone. */
function dimmed(task: TaskListRow): boolean {
  return isTerminal(task.status) || task.deleted_at !== null
}

/**
 * The deadline has passed and the work is not closed. Only this case is colored: every deadline in
 * a warning color would shout about all tasks at once and therefore about none.
 */
function overdue(task: TaskListRow): boolean {
  if (!task.deadline_at || isTerminal(task.status) || task.deleted_at) return false
  // Dates arrive in UTC SQL format (`YYYY-MM-DD HH:MM:SS`) — it compares as a string.
  return task.deadline_at < new Date().toISOString().slice(0, 19).replace('T', ' ')
}

/** The row's date is the task deadline; without one there is nothing to show in this column. */
function dateOf(task: TaskListRow): { value: string; label: string } | null {
  if (task.deadline_at) return { value: task.deadline_at, label: t('tasks.task.card.deadline_at') }
  return null
}

// Open action menu: the row keeps its "⋯" visible while the menu is open — otherwise the button
// would vanish from under the cursor as soon as it moved onto a menu item.
const menuOpen = ref(false)
</script>

<template>
  <div
    class="task-row"
    :class="{
      'task-row--dimmed': dimmed(props.task),
      'task-row--open': props.open,
      'task-row--child': props.depth > 0,
      'task-row--last-child': props.depth > 0 && props.last,
    }"
    :style="{ '--row-depth': props.depth }"
    role="link"
    tabindex="0"
    @click="emit('open', props.task.code)"
    @keydown.enter="emit('open', props.task.code)"
  >
    <!-- A subtask has a handle too: its row is its siblings, and it is reordered by the same
         gesture. The handle's slot is always occupied — the row must not twitch on hover. -->
    <DragHandle
      v-if="!props.task.deleted_at && props.reorderable !== false"
      :label="t('tasks.task.card.drag')"
      @click.stop
    />
    <span v-else class="task-row__handle-gap" />

    <!-- State is a glyph, not a word: a shape is recognised in peripheral vision, and the icon
         column is scanned top to bottom without reading. The name stays as a tooltip — and as
         `aria-label`: the tooltip comes on hover, while a screen reader needs the same word the
         eye sees. The same goes for every other glyph in the row. -->
    <span
      class="task-row__glyph"
      :class="`task-row__glyph--${statusColor(props.task.status)}`"
      role="img"
      :aria-label="t(`tasks.task.status.${props.task.status}`)"
    >
      <component :is="statusIcon(props.task.status)" :size="18" :stroke-width="1.6" />
      <VTooltip activator="parent" location="top">
        {{ t(`tasks.task.status.${props.task.status}`) }}
      </VTooltip>
    </span>

    <span
      class="task-row__glyph"
      :class="`task-row__glyph--${priorityColor(props.task.priority)}`"
      role="img"
      :aria-label="t(`tasks.task.priority.${props.task.priority}`)"
    >
      <component :is="priorityIcon(props.task.priority)" :size="16" :stroke-width="1.6" />
      <VTooltip activator="parent" location="top">
        {{ t(`tasks.task.priority.${props.task.priority}`) }}
      </VTooltip>
    </span>

    <!-- The title followed by the subtask count. Everything sits RIGHT after the text, as on a
         group card, not at the row's edge. A long title shrinks with an ellipsis, the count never
         does: in a collapsed branch it is the only trace of it. -->
    <span class="task-row__name">
      <span class="task-row__title" :title="props.task.title">{{ props.task.title }}</span>
      <!-- When the branch is drawn, count and arrow are one button, the same as on a group header. -->
      <CounterButton
        v-if="props.foldable"
        class="task-row__fold"
        :icon="IconSubtask"
        :count="props.childCount || undefined"
        :folded="folded"
        :label="t(folded ? 'tasks.task.card.expand_children' : 'tasks.task.card.collapse_children')"
        @toggle="store.toggleCollapsed(props.task.code)"
      />
      <!-- No branch on screen (narrowed results) — nothing to collapse, so the count stays a mark. -->
      <span
        v-else-if="props.childCount || props.task.has_children"
        class="task-row__mark task-row__children"
        :aria-label="t('tasks.task.detail.children')"
      >
        <IconSubtask :size="14" :stroke-width="1.6" />
        <span v-if="props.childCount">{{ props.childCount }}</span>
        <VTooltip activator="parent" location="top">{{ t('tasks.task.detail.children') }}</VTooltip>
      </span>
    </span>

    <span class="task-row__meta">
      <!-- The trash is a mark too, not a badge: the row is already muted as a whole, and the icon
           only has to say WHY it is muted. -->
      <span
        v-if="props.task.deleted_at"
        class="task-row__mark"
        role="img"
        :aria-label="t('tasks.task.card.deleted')"
      >
        <IconTrash :size="14" :stroke-width="1.6" />
        <VTooltip activator="parent" location="top">{{ t('tasks.task.card.deleted') }}</VTooltip>
      </span>

      <span
        v-if="dateOf(props.task)"
        class="task-row__date"
        :class="{ 'task-row__date--overdue': overdue(props.task) }"
        :aria-label="`${dateOf(props.task)!.label}: ${fmtDate(dateOf(props.task)!.value)}`"
      >
        {{ fmtDateShort(dateOf(props.task)!.value) }}
        <VTooltip activator="parent" location="top">
          {{ dateOf(props.task)!.label }}: {{ fmtDate(dateOf(props.task)!.value) }}
        </VTooltip>
      </span>
    </span>

    <!-- The menu is a utility gutter, not data: a click on it must not open the task. Three dots
         on every row are constant noise, so the button appears under the cursor and stays while
         the menu is open. -->
    <span
      class="task-row__menu"
      :class="{ 'task-row__menu--open': menuOpen }"
      @click.stop
    >
      <VMenu v-model="menuOpen" location="bottom end" :offset="4">
        <template #activator="{ props: menu }">
          <VBtn
            v-bind="menu"
            icon
            variant="text"
            class="row-action"
            :title="t('tasks.task.card.actions')"
          >
            <IconDotsVertical :size="16" :stroke-width="1.6" />
          </VBtn>
        </template>

        <!-- The action set depends on state: a live task gets reorder, edit, subtask and delete,
             a deleted one gets only restore. The backend refuses to edit a deleted task (409), and
             an item bound to fail would make the button lie. -->
        <VList density="compact">
          <template v-if="!props.task.deleted_at">
            <!-- Mouseless reordering disappears together with the handle: on a narrowed list the
                 order is changed neither by gesture nor by menu item. -->
            <template v-if="props.reorderable !== false">
              <VListItem
                :prepend-icon="IconArrowUp"
                :disabled="!props.canUp"
                @click="emit('step', -1)"
              >
                <VListItemTitle>{{ t('tasks.task.card.move_up') }}</VListItemTitle>
              </VListItem>
              <VListItem
                :prepend-icon="IconArrowDown"
                :disabled="!props.canDown"
                @click="emit('step', 1)"
              >
                <VListItemTitle>{{ t('tasks.task.card.move_down') }}</VListItemTitle>
              </VListItem>
              <!-- Detaching is the same as dragging up with the mouse, only without a drop point:
                   the task becomes first in its group so the result is visible at once. Having a
                   parent decides, not the row depth: on the task page its direct subtasks form the
                   branch's top row, yet they can be detached just the same. -->
              <VListItem
                v-if="props.task.parent_code !== null"
                :prepend-icon="IconUnlink"
                @click="emit('detach')"
              >
                <VListItemTitle>{{ t('tasks.task.card.detach') }}</VListItemTitle>
              </VListItem>
              <VDivider class="my-1" />
            </template>
            <VListItem :prepend-icon="IconPencil" @click="emit('edit', props.task)">
              <VListItemTitle>{{ t('tasks.task.card.edit') }}</VListItemTitle>
            </VListItem>
            <VListItem :prepend-icon="IconSubtask" @click="emit('addChild', props.task)">
              <VListItemTitle>{{ t('tasks.task.card.add_child') }}</VListItemTitle>
            </VListItem>
            <VListItem
              :prepend-icon="IconTrash"
              class="task-menu-danger"
              @click="emit('remove', props.task.code)"
            >
              <VListItemTitle>{{ t('tasks.task.card.delete') }}</VListItemTitle>
            </VListItem>
          </template>
          <VListItem
            v-else
            :prepend-icon="IconRestore"
            @click="emit('restore', props.task.code)"
          >
            <VListItemTitle>{{ t('tasks.task.card.restore') }}</VListItemTitle>
          </VListItem>
        </VList>
      </VMenu>
    </span>
  </div>
</template>

<style scoped>
/* Exactly 36px and one line of content. The divider is a hairline between adjacent rows: zebra
   striping paints half the list for no reason, and a border on every row turns the list into a
   stack of cards. The line is drawn on top, not at the bottom: a row's neighbours can be subtask
   containers and branch wrappers alike, and "each has its own top border" is the only rule that
   holds in any order of them. */
.task-row {
  /* The branch offset is set here, not as padding on every level: the row brings its depth along
     as a variable, and any nesting level is computed with one multiplication. */
  --row-indent: 22px;

  position: relative;
  display: flex;
  align-items: center;
  gap: 8px;
  height: 36px;
  padding: 0 8px 0 calc(6px + var(--row-depth, 0) * var(--row-indent));
  /* The row is a link: a click opens the task, and the cursor must promise that. The handle, the
     counter button and the menu set their own cursor on top — they have a different action. */
  cursor: pointer;
}

.task-row:hover,
.task-row:focus-visible { background: var(--surface-hi); outline: none; }

/* The opened task stays marked after the cursor has left: on return the person sees where they
   went from. A stripe on the left, not only a background — otherwise the mark looks like hover. */
.task-row--open {
  background: var(--surface-hi);
  box-shadow: inset 2px 0 0 var(--accent);
}

/* Closed work and the trash are muted as a whole, not marked with a single label: such rows must
   not compete for attention with live ones. Hover restores opacity — reading a row does not
   require resurrecting it. */
.task-row--dimmed { opacity: 0.55; }
.task-row--dimmed:hover { opacity: 1; }

/* An empty slot in place of the handle: a deleted task has none, but row columns must align. */
.task-row__handle-gap {
  width: 20px;
  flex: none;
}

/* A subtask's handle is pushed past the guide's bend: the bend ends 9px right of the vertical,
   and an unindented handle would start earlier — the grip icon would sit right on the branch line.
   The empty handle slot shifts too, otherwise a deleted subtask's columns would drift apart. */
.task-row--child .drag-handle,
.task-row--child .task-row__handle-gap {
  margin-inline-start: 8px;
}

/* The branch guide: a vertical from the previous row and a bend toward the state icon. The
   pseudo-element does not catch the pointer: the whole row is clickable, and the line must be no
   exception. */
.task-row--child::before {
  content: '';
  position: absolute;
  top: 0;
  bottom: 50%;
  left: calc(16px + (var(--row-depth, 1) - 1) * var(--row-indent) + 9px);
  width: 9px;
  border-left: 1px solid var(--border);
  border-bottom: 1px solid var(--border);
  border-bottom-left-radius: 6px;
  pointer-events: none;
}

/* The last child cuts the vertical off at its bend, the others continue it down — otherwise the
   line would end where the branch still goes on. */
.task-row--child:not(.task-row--last-child)::after {
  content: '';
  position: absolute;
  top: 50%;
  bottom: 0;
  left: calc(16px + (var(--row-depth, 1) - 1) * var(--row-indent) + 9px);
  border-left: 1px solid var(--border);
  pointer-events: none;
}

/* The state glyph and the importance glyph: the only two places in the row with color. */
.task-row__glyph {
  display: inline-flex;
  align-items: center;
  flex: none;
}

.task-row__glyph--accent  { color: var(--accent); }
.task-row__glyph--success { color: var(--success); }
.task-row__glyph--error   { color: var(--error); }
.task-row__glyph--warn    { color: var(--warn); }
.task-row__glyph--muted   { color: var(--text-faint); }

/* The title is regular weight and the primary color: it is the row, everything around it is
   auxiliary. Semibold would work on a card, but in a list of a hundred rows the whole screen ends
   up bold. */
.task-row__title {
  flex: 0 1 auto;
  min-width: 0;
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
  font-size: 13px;
  color: var(--text);
}

/* The title cell takes the rest of the row, while the title inside takes only its own width: this
   puts the arrow right after the text, not at the right edge. */
.task-row__name {
  display: flex;
  align-items: center;
  gap: 2px;
  flex: 1 1 auto;
  min-width: 0;
}

/* The subtask count moved from the marks to the title but remains a mark: the same size and the
   same muted color as the others on the right — otherwise it would read as a continuation of the
   title. The left margin sets it off from the text; the cell gap is enough before the arrow. */
.task-row__children {
  flex: none;
  margin-inline-start: 6px;
  font-size: 12px;
  color: var(--text-faint);
}

/* The branch button's look is its own (`CounterButton`); the row sets only its place: a negative
   margin hides the button's padding, so the icon sits as far from the text as the passive count
   above. The row also reveals it while the cursor is over the row. */
.task-row__fold { margin-inline: 2px -4px; }

.task-row:hover { --counter-button-color: var(--text-muted); }

.task-row__meta {
  display: inline-flex;
  align-items: center;
  gap: 10px;
  flex: none;
  font-size: 12px;
  color: var(--text-faint);
}

.task-row__mark {
  display: inline-flex;
  align-items: center;
  gap: 3px;
}

.task-row__date { font-variant-numeric: tabular-nums; }

/* The only mark entitled to color: the deadline has passed and the work is still open. */
.task-row__date--overdue { color: var(--warn); }

.task-row__menu {
  display: inline-flex;
  flex: none;
  width: 28px;
  opacity: 0;
  transition: opacity 0.12s ease;
}

.task-row:hover .task-row__menu,
.task-row:focus-within .task-row__menu,
.task-row__menu--open { opacity: 1; }

.task-row__menu :deep(.v-btn) {
  width: 28px;
  min-width: 28px;
  height: 28px;
}

.task-menu-danger :deep(.v-list-item-title) { color: var(--error); }
.task-menu-danger :deep(.v-list-item__prepend) { color: var(--error); }
</style>
