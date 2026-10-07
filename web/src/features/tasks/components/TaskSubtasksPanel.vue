<script setup lang="ts">
// Subtasks on the task page — in the same form as in the main list.
//
// One card: search and "show beyond the usual" on top, the branch below. Rows are the same
// `TaskRow`, the container is the same `TaskSubtree` that draws the branch under a task in the
// list: a subtask must look and move the same wherever it is seen. The branch root here is the
// open task itself, so the gestures are the same as inside a list branch: reordering among
// siblings is allowed, dropping into another branch is not.
//
// Search turns the branch into a flat row of matches and disables reordering — like the filter in
// the list: in a row where not all siblings are present, "land after a neighbour" means something
// other than what is visible.
import { computed, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { IconCircleCheck, IconTrash } from '@tabler/icons-vue'

import SearchField from '@/components/SearchField.vue'
import { useChangeSubscription } from '@/composables/useChangeSubscription'
import type { Change } from '@/stores/changes'

import TaskRow from './TaskRow.vue'
import TaskSubtree from './TaskSubtree.vue'
import { useTaskSubtreeStore } from '../stores/task-subtree.store'
import type { TaskListRow } from '../api'

const props = defineProps<{
  /** The open task — the branch root. */
  taskCode: string
  workspace: string
  /** The task is in the trash: its branch was deleted with it and is visible only with deleted. */
  deleted: boolean
}>()

const emit = defineEmits<{
  open: [code: string]
  edit: [task: TaskListRow]
  addChild: [task: TaskListRow]
}>()

const { t } = useI18n()
const store = useTaskSubtreeStore()

// Sources are watched separately, not as one array: an array from a getter is new on every read,
// and a re-read of the task card (live update) would reopen the branch even though no value
// changed.
watch(
  [() => props.taskCode, () => props.workspace, () => props.deleted],
  ([code, workspace, deleted]) => {
    if (code && workspace) void store.open(code, workspace, deleted)
  },
  { immediate: true },
)

// Keys of the "show beyond the usual" group — the same two buttons as in the list filter panel.
const EXTRA_FINISHED = 'finished'
const EXTRA_DELETED = 'deleted'

/** Pressed button = shown; the store flags' polarity is inverted here, as in `TaskFilters`. */
const extras = computed({
  get: () => [
    ...(store.hideFinished ? [] : [EXTRA_FINISHED]),
    ...(store.deletedShown ? [EXTRA_DELETED] : []),
  ],
  set: (keys: string[]) => {
    store.hideFinished = !keys.includes(EXTRA_FINISHED)
    const deleted = keys.includes(EXTRA_DELETED)
    if (deleted !== store.includeDeleted) void store.showDeleted(deleted)
  },
})

async function move(payload: {
  code: string
  after: string | null
  parent?: string | null
  group?: string | null
}) {
  await store.reorder(payload.code, payload.after, {
    ...('group' in payload ? { group: payload.group } : {}),
    ...('parent' in payload ? { parent: payload.parent } : {}),
  })
}

defineExpose({ reload: () => store.load() })

// The branch updates itself when someone else (the agent, another tab) changes tasks or their
// positions. The branch is built from the workspace's flat list, so "ours" is anything from this
// workspace: a new task carries it in `refs`, while a tree edge carries only task codes and is
// recognised by the ones already known.
function concernsBranch(change: Change): boolean {
  if (change.ids.length === 0) return true
  if (change.refs.includes(props.workspace)) return true
  const known = new Set(store.items.map((task) => task.code))
  return [...change.ids, ...change.refs].some((code) => known.has(code))
}

useChangeSubscription({
  entities: ['tasks.task', 'tasks.link'],
  match: concernsBranch,
  onChange: () => void store.load(),
  onResync: () => void store.load(),
})
</script>

<template>
  <!-- No subtasks at all — no card either: a search and toggles over emptiness promise a list
       that does not exist. What remains is a line, as with an empty journal. While the branch is
       loading nothing is shown: otherwise a task with subtasks would flash "no subtasks". -->
  <p v-if="store.isEmpty" v-show="!store.loading" class="subtasks-empty">
    {{ t('tasks.task.detail.no_children') }}
  </p>

  <VCard v-else variant="outlined" rounded="lg" class="subtasks">
    <div class="subtasks__toolbar">
      <SearchField
        v-model="store.query"
        :placeholder="t('tasks.task.detail.children_query')"
        density="compact"
        class="subtasks__search"
      />

      <!-- A task in the trash has no live subtasks at all, so "Deleted" cannot be switched off
           for it: without them the branch would be empty, though under the task lies everything
           that will come back with it. -->
      <VBtnToggle
        v-model="extras"
        multiple
        variant="outlined"
        divided
        density="compact"
        color="primary"
        class="subtasks__extras"
      >
        <VBtn :value="EXTRA_FINISHED" size="small">
          <template #prepend><IconCircleCheck :size="16" :stroke-width="1.7" /></template>
          {{ t('tasks.task.filter.finished') }}
        </VBtn>
        <VBtn :value="EXTRA_DELETED" size="small" :disabled="store.rootDeleted">
          <template #prepend><IconTrash :size="16" :stroke-width="1.7" /></template>
          {{ t('tasks.task.filter.deleted') }}
        </VBtn>
      </VBtnToggle>
    </div>

    <VProgressLinear v-if="store.loading" indeterminate height="2" class="subtasks__progress" />

    <p v-if="store.isFilteredOut" class="subtasks__state">
      {{ t('tasks.task.detail.children_filtered') }}
    </p>

    <!-- Search matches as a flat row without handles: see the file header. -->
    <div v-else-if="store.searching" class="subtasks__flat">
      <div v-for="task in store.matches" :key="task.code" class="subtasks__flat-item">
        <TaskRow
          :task="task"
          :depth="0"
          :last="true"
          :child-count="store.childCounts.get(task.code) ?? 0"
          :reorderable="false"
          @open="emit('open', $event)"
          @edit="emit('edit', $event)"
          @add-child="emit('addChild', $event)"
          @remove="store.remove($event)"
          @restore="store.restore($event)"
        />
      </div>
    </div>

    <TaskSubtree
      v-else
      :nodes="store.nodes"
      :parent-code="props.taskCode"
      :child-counts="store.childCounts"
      :reorderable="!props.deleted"
      @open="emit('open', $event)"
      @edit="emit('edit', $event)"
      @add-child="emit('addChild', $event)"
      @remove="store.remove($event)"
      @restore="store.restore($event)"
      @move="move"
    />
  </VCard>
</template>

<style scoped>
/* Same look as the empty journal (`TaskJournal`, `.journal__empty`): neighbouring page sections
   say "empty" in one voice. */
.subtasks-empty {
  margin: 0;
  font-size: 13px;
  color: var(--text-muted);
}

/* The controls row is like the list filter panel (`filter-panel` + `TaskFilters`): search on the
   left, toggles hugging the right edge, wrapping as a whole in a narrow window. */
.subtasks__toolbar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  padding: 10px 12px;
}

/* The task page column is narrower than the list: the search gives up width first, otherwise the
   toggles moved to a second line even though they had room. */
.subtasks__search {
  flex: 1 1 200px;
  max-width: 364px;
  min-width: 180px;
}

.subtasks__search :deep(.v-field__input) { font-size: 13px; }
.subtasks__search :deep(.v-field__prepend-inner) { color: var(--text-faint); }

.subtasks__extras {
  flex: none;
  margin-inline-start: auto;
}

.subtasks__extras :deep(.v-btn) { font-size: 12px; }

/* The progress bar does not push the card apart: a re-read after every gesture would jolt rows. */
.subtasks__progress {
  position: absolute;
  top: 0;
  left: 0;
  z-index: 1;
}

.subtasks__state {
  margin: 0;
  padding: 16px 12px;
  border-top: 1px solid var(--border-soft);
  font-size: 13px;
  color: var(--text-muted);
}

/* Flat-row dividers match the branch's (`TaskSubtree`): a line above every row, the first one
   included — it also separates the row from the controls panel. */
.subtasks__flat-item {
  border-top: 1px solid var(--border-soft);
}
</style>
