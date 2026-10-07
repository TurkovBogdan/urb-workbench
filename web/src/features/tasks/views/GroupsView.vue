<script setup lang="ts">
// Groups of the current workspace: full-width rows in the order the task list shows them, the same
// list as the workspaces page (`EntityRowList`); one form dialog for create and edit, a
// confirmation for each of the two deletions.
//
// A group is a long-lived topic inside a workspace ("billing", "interface"), and the task list is
// split into sections by it. Hence the binding: the section shows the groups of the workspace
// selected in the sidebar and has no workspace picker of its own — a second such picker would
// diverge from the first at the very first switch.
//
// Deleted groups sit in the same list behind a toggle in the search toolbar, not on a separate
// page: they arrive with the same request plus a flag.
import { computed, onActivated, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { IconPlus, IconRefresh } from '@tabler/icons-vue'

import PageLayout from '@/layout/templates/PageLayout.vue'
import PageHeader from '@/layout/components/PageHeader.vue'
import ConfirmDialog from '@/components/ConfirmDialog.vue'
import EntityRowList, { type EntityRowCounter, type EntityRowLabels } from '@/components/EntityRowList.vue'
import EntityRowListSkeleton from '@/components/EntityRowListSkeleton.vue'
import SectionError from '@/components/SectionError.vue'
import { useChangeSubscription } from '@/composables/useChangeSubscription'
import { useFindShortcut } from '@/composables/useFindShortcut'
import type { Change } from '@/stores/changes'

import GroupFilters from '../components/GroupFilters.vue'
import GroupFormDialog from '../components/GroupFormDialog.vue'
import GroupDeleteDialog from '../components/GroupDeleteDialog.vue'
import { deleteGroup, purgeGroup, type GroupListRow, type GroupTaskDisposal } from '../api'
import { useGroupsStore } from '../stores/groups.store'
import { useWorkspaceContextStore } from '@/features/workspace/stores/workspace-context.store'

const { t } = useI18n()
const store = useGroupsStore()
const context = useWorkspaceContextStore()

function counters(group: GroupListRow): EntityRowCounter[] {
  return [{ key: 'tasks', count: group.task_count, label: t('tasks.group.card.tasks', group.task_count) }]
}

const labels = computed<EntityRowLabels>(() => ({
  drag: t('tasks.group.card.drag'),
  deleted: t('tasks.group.card.deleted'),
  actions: t('tasks.group.card.actions'),
  updatedAt: t('tasks.group.card.updated_at'),
  edit: t('tasks.group.card.edit'),
  delete: t('tasks.group.card.delete'),
  restore: t('tasks.group.card.restore'),
  purge: t('tasks.group.card.purge'),
}))

// The page lives in KeepAlive and is not unmounted between navigations. `onActivated` fires both on
// first display and on every return, otherwise the list would stay stale; a second call from
// `onMounted` would send two identical requests in a row on first display.
onActivated(store.load)

const filters = ref<InstanceType<typeof GroupFilters> | null>(null)
useFindShortcut(filters)

const workspace = computed(() => context.currentWorkspace?.code ?? '')

// ── Live updates ──────────────────────────────────────────────────────────────
// The section re-reads itself when someone else changes groups. Tasks are listened to as well:
// the card carries their count, which changes when a task is created, moved or deleted. "Ours" is
// anything from the current workspace (`refs`) or the codes of groups already shown. A bulk
// operation (deleting and restoring a task branch, purging a group) arrives without `refs`, and
// whose it is cannot be told: such a change is taken.
function concernsGroups(change: Change): boolean {
  if (change.ids.length === 0 || change.refs.length === 0) return true
  if (workspace.value && change.refs.includes(workspace.value)) return true
  const known = new Set(store.items.map((group) => group.code))
  return [...change.ids, ...change.refs].some((code) => known.has(code))
}

useChangeSubscription({
  entities: ['tasks.group', 'tasks.task'],
  match: concernsGroups,
  // Our own drops come back through the feed too; while they are on their way a re-read would show
  // the order the backend has not reached yet, and the reorder re-reads once it has drained.
  onChange: () => { if (!store.moving) void store.load() },
  onResync: () => void store.load(),
  reloadsOnReturn: true,
})

const editing = ref<GroupListRow | null>(null)
const removing = ref<GroupListRow | null>(null)
const purging = ref<GroupListRow | null>(null)
const formOpen = ref(false)
const deleteOpen = ref(false)
const purgeOpen = ref(false)
const busy = ref(false)

function create() {
  editing.value = null
  formOpen.value = true
}

function edit(group: GroupListRow) {
  editing.value = group
  formOpen.value = true
}

function askRemove(group: GroupListRow) {
  removing.value = group
  deleteOpen.value = true
}

function askPurge(group: GroupListRow) {
  purging.value = group
  purgeOpen.value = true
}

// Both deletions close the dialog only on success: on refusal it stays open and the message is
// shown by the client's toast — the confirmation has no place of its own for it.
async function remove(fate: { tasks?: GroupTaskDisposal; target?: string }) {
  const group = removing.value
  if (!group) return
  busy.value = true
  try {
    await deleteGroup(group.code, fate)
    deleteOpen.value = false
    await store.load()
  } finally {
    busy.value = false
  }
}

async function purge() {
  const group = purging.value
  if (!group) return
  busy.value = true
  try {
    await purgeGroup(group.code)
    purgeOpen.value = false
    await store.load()
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <PageLayout>
    <PageHeader
      :title="t('tasks.group.list.title')"
      :description="t('tasks.group.list.description')"
    >
      <template #actions>
        <VBtn variant="text" :disabled="store.loading" @click="store.load">
          <template #prepend><IconRefresh :size="16" :class="{ 'icon-spin': store.loading }" /></template>
          {{ t('tasks.action.refresh') }}
        </VBtn>
        <VBtn color="primary" variant="flat" :disabled="!workspace" @click="create">
          <template #prepend><IconPlus :size="16" /></template>
          {{ t('tasks.group.list.add') }}
        </VBtn>
      </template>
    </PageHeader>

    <!-- The search toolbar is its own card ABOVE the list, the same anatomy as the task list
         (`FilterPanel` + cards below it). Without a workspace there is nowhere to search, so it
         is absent. -->
    <GroupFilters v-if="!store.noWorkspace" ref="filters" class="mb-3" />

    <!-- No workspaces at all: groups have nowhere to live, and offering to create a group here
         would lead into a refusal. Point to where workspaces are created instead. -->
    <div v-if="store.noWorkspace" class="groups-empty">
      <p class="groups-empty__title">{{ t('tasks.task.list.no_workspace') }}</p>
      <p class="groups-empty__hint">{{ t('tasks.task.list.no_workspace_hint') }}</p>
      <VBtn color="primary" variant="flat" to="/workspaces">
        {{ t('tasks.task.list.to_workspaces') }}
      </VBtn>
    </div>

    <EntityRowListSkeleton v-else-if="store.loading" />

    <SectionError v-else-if="store.error" :error="store.error" />

    <div v-else-if="store.isEmpty" class="groups-empty">
      <p class="groups-empty__title">{{ t('tasks.group.list.empty') }}</p>
      <p class="groups-empty__hint">{{ t('tasks.group.list.empty_hint') }}</p>
      <VBtn color="primary" variant="flat" @click="create">
        <template #prepend><IconPlus :size="16" /></template>
        {{ t('tasks.group.list.add') }}
      </VBtn>
    </div>

    <!-- Groups exist but the search left none: the way out is clearing the search, not creating a
         group. -->
    <div v-else-if="store.isFilteredOut" class="groups-empty">
      <p class="groups-empty__title">{{ t('tasks.group.list.nothing_found') }}</p>
      <VBtn variant="text" size="small" @click="store.query = ''">
        {{ t('tasks.group.list.clear_search') }}
      </VBtn>
    </div>

    <EntityRowList
      v-else
      :items="store.visible"
      :reorderable="store.reorderable"
      :counters="counters"
      :labels="labels"
      @edit="edit"
      @remove="askRemove"
      @restore="(group) => store.restore(group.code)"
      @purge="askPurge"
      @move="store.move"
    />

    <GroupFormDialog
      v-model="formOpen"
      :workspace="workspace"
      :group="editing"
      @saved="store.load"
    />

    <!-- Deleting a group names what becomes of its tasks: left pointing at a deleted group they
         would vanish from the list. -->
    <GroupDeleteDialog
      v-model="deleteOpen"
      :group="removing"
      :groups="store.items"
      :loading="busy"
      @confirm="remove"
    />

    <ConfirmDialog
      v-model="purgeOpen"
      :title="t('tasks.group.purge.title')"
      :text="t('tasks.group.purge.text', purging?.task_count ?? 0)"
      :confirm-label="t('tasks.group.card.purge')"
      :loading="busy"
      @confirm="purge"
    />
  </PageLayout>
</template>

<style scoped>
.groups-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 8px;
  min-height: 200px;
  text-align: center;
}

.groups-empty__title {
  margin: 0;
  font-size: 15px;
  font-weight: 600;
  color: var(--text);
}

.groups-empty__hint {
  margin: 0 0 8px;
  font-size: 13px;
  color: var(--text-muted);
}
</style>
