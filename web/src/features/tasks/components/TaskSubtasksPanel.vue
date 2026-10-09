<script setup lang="ts">
// Subtasks on the task page — in the same form as in the main list.
//
// One card: the section header on top, the branch below — no search and no filters, a task's
// subtasks are few enough to be read through. Finished ones are shown, deleted ones are not. Rows are the same `TaskRow`, the container is
// the same `TaskSubtree` that draws the branch under a task in the list: a subtask must look and
// move the same wherever it is seen. The branch root here is the open task itself, so the gestures
// are the same as inside a list branch: reordering among siblings is allowed, dropping into another
// branch is not.
import { watch } from 'vue'
import { useI18n } from 'vue-i18n'

import { useChangeSubscription } from '@/composables/useChangeSubscription'
import type { Change } from '@/stores/changes'

import CollectionHeader from './CollectionHeader.vue'
import TaskSubtree from './TaskSubtree.vue'
import { useTaskSubtreeStore } from '../stores/task-subtree.store'
import type { TaskListRow } from '../api'

const props = defineProps<{
  /** The open task — the branch root. */
  taskCode: string
  workspace: string
  /** The task is in the trash: its branch was deleted with it and is visible only with deleted. */
  deleted: boolean
  /** A subtask may be added here: the task is live and not a subtask itself (the tree is one level deep). */
  addable: boolean
}>()

const emit = defineEmits<{
  open: [code: string]
  /** Add a subtask to the open task — the header's button. */
  add: []
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
  <!-- The card is there even with no subtasks: it holds the header, and the header holds the add
       button. The rows below draw a line above each one, the first one included — it separates
       the branch from the header. -->
  <VCard variant="outlined" rounded="lg" class="subtasks">
    <div class="subtasks__head">
      <CollectionHeader
        :title="t('tasks.task.detail.children')"
        :hint="t('tasks.task.detail.hint.children')"
        :add-label="props.addable ? t('tasks.task.card.add_child') : undefined"
        in-card
        @add="emit('add')"
      />
    </div>

    <VProgressLinear v-if="store.loading" indeterminate height="2" class="subtasks__progress" />

    <TaskSubtree
      :nodes="store.nodes"
      :parent-code="props.taskCode"
      :child-counts="store.childCounts"
      :reorderable="!props.deleted"
      @open="emit('open', $event)"
      @add-child="emit('addChild', $event)"
      @remove="store.remove($event)"
      @restore="store.restore($event)"
      @status="store.setStatus($event.code, $event.status)"
      @move="move"
    />
  </VCard>
</template>

<style scoped>
/* 16px on the left, as in the text cards above: the title stands on the line of theirs. The right
   side is tighter — the text button's own padding makes up the rest. */
.subtasks__head {
  padding: 12px 12px 12px 16px;
}

/* A finished subtask is not muted here, unlike in the list: there it makes room for live work
   among everything else, here it is part of what the task is made of and is read as much as an
   open one. Its status glyph already says it is closed. */
.subtasks :deep(.task-row--dimmed) { opacity: 1; }

/* The progress bar does not push the card apart: a re-read after every gesture would jolt rows. */
.subtasks__progress {
  position: absolute;
  top: 0;
  left: 0;
  z-index: 1;
}
</style>
