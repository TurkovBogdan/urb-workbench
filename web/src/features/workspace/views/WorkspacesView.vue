<script setup lang="ts">
// Workspaces: a list of full-width rows (`EntityRowList` — the rows and their drag order), one form
// dialog for create and edit, two delete dialogs — reversible and final.
//
// A workspace is the top level of data isolation, shared by all application modules. The page
// doesn't know what exactly is inside: a row shows the counters declared by the modules on top
// (`counters` in the list row). Without them "delete" would be an offer to confirm the unknown, and
// with zones and tasks enumerated right here the page would need editing for every new module.
//
// Deleted ones sit in the same list, not on a separate page: they arrive with the same request
// plus a flag, and splitting them across addresses would mean a second list for the same rows.
import { computed, onActivated, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { IconPlus, IconRefresh } from '@tabler/icons-vue'

import PageLayout from '@/layout/templates/PageLayout.vue'
import PageHeader from '@/layout/components/PageHeader.vue'
import SectionError from '@/components/SectionError.vue'
import EntityRowList, { type EntityRowCounter, type EntityRowLabels } from '@/components/EntityRowList.vue'
import EntityRowListSkeleton from '@/components/EntityRowListSkeleton.vue'
import { useFindShortcut } from '@/composables/useFindShortcut'
import { pushToast } from '@/composables/useToasts'

import WorkspaceFilters from '../components/WorkspaceFilters.vue'
import WorkspaceFormDialog from '../components/WorkspaceFormDialog.vue'
import WorkspaceDeleteDialog from '../components/WorkspaceDeleteDialog.vue'
import WorkspacePurgeDialog from '../components/WorkspacePurgeDialog.vue'
import { useWorkspacesStore } from '../stores/workspaces.store'
import type { WorkspaceListRow } from '../api'

const { t } = useI18n()
const store = useWorkspacesStore()

// The page doesn't list what is counted: the modules on top declare the set, and each counter
// arrives with the key of its declined label.
function counters(workspace: WorkspaceListRow): EntityRowCounter[] {
  return workspace.counters.map((counter) => ({
    key: counter.key,
    count: counter.count,
    label: t(counter.label_key, counter.count),
  }))
}

const labels = computed<EntityRowLabels>(() => ({
  drag: t('workspace.card.drag'),
  deleted: t('workspace.card.deleted'),
  actions: t('workspace.card.actions'),
  updatedAt: t('workspace.card.updated_at'),
  edit: t('workspace.card.edit'),
  delete: t('workspace.card.delete'),
  restore: t('workspace.card.restore'),
  purge: t('workspace.card.purge'),
}))

// The page lives in KeepAlive and isn't unmounted between transitions. `onActivated` fires both on
// first show and on every return, otherwise the list would stay stale; a second call from
// `onMounted` would make two identical requests in a row on first show.
onActivated(store.load)

const filters = ref<InstanceType<typeof WorkspaceFilters> | null>(null)
useFindShortcut(filters)

const editing = ref<WorkspaceListRow | null>(null)
const removing = ref<WorkspaceListRow | null>(null)
const purging = ref<WorkspaceListRow | null>(null)
const formOpen = ref(false)
const deleteOpen = ref(false)
const purgeOpen = ref(false)

// Create and edit are one dialog: an empty card differs from a filled one only in that it has no
// workspace yet.
function create() {
  editing.value = null
  formOpen.value = true
}

function edit(workspace: WorkspaceListRow) {
  editing.value = workspace
  formOpen.value = true
}

function remove(workspace: WorkspaceListRow) {
  removing.value = workspace
  deleteOpen.value = true
}

/** Longer than the default 5 s: the person has to read the line and reach for the button. */
const UNDO_TIMEOUT = 8000

// A soft delete is answered with the way back right where the eye is: the row has just vanished,
// and the trash filter is two clicks away from a person who only now noticed the wrong row.
function onDeleted(workspace: WorkspaceListRow) {
  void store.load()
  const title = workspace.title
  pushToast(t('workspace.delete.done', { title }), 'success', UNDO_TIMEOUT, {
    label: t('workspace.delete.undo'),
    run: async () => {
      if (await store.restore(workspace.code)) {
        pushToast(t('workspace.delete.restored', { title }), 'success')
      }
    },
  })
}

function purge(workspace: WorkspaceListRow) {
  purging.value = workspace
  purgeOpen.value = true
}
</script>

<template>
  <PageLayout>
    <PageHeader
      :title="t('workspace.list.title')"
      :description="t('workspace.list.description')"
    >
      <template #actions>
        <VBtn variant="text" :disabled="store.loading" @click="store.load">
          <template #prepend><IconRefresh :size="16" :class="{ 'icon-spin': store.loading }" /></template>
          {{ t('workspace.list.refresh') }}
        </VBtn>
        <VBtn color="primary" variant="flat" @click="create">
          <template #prepend><IconPlus :size="16" /></template>
          {{ t('workspace.list.add') }}
        </VBtn>
      </template>
    </PageHeader>

    <!-- The search toolbar is its own card ABOVE the list — the anatomy of the groups page and
         the task list (`FilterPanel` + cards below it). The trash toggle lives here too, not in
         the header: it narrows what the list shows, like the search. -->
    <WorkspaceFilters ref="filters" class="mb-3" />

    <EntityRowListSkeleton v-if="store.loading" />

    <SectionError v-else-if="store.error" :error="store.error" />

    <!-- The empty state invites creating the first workspace: a list that offers nothing leaves
         the person guessing what is missing here. -->
    <div v-else-if="store.isEmpty" class="workspaces-empty">
      <p class="workspaces-empty__title">{{ t('workspace.list.empty') }}</p>
      <p class="workspaces-empty__hint">{{ t('workspace.list.empty_hint') }}</p>
      <VBtn color="primary" variant="flat" @click="create">
        <template #prepend><IconPlus :size="16" /></template>
        {{ t('workspace.list.add') }}
      </VBtn>
    </div>

    <!-- Workspaces exist but the search left none: the way out is clearing the search, not
         creating a workspace. -->
    <div v-else-if="store.isFilteredOut" class="workspaces-empty">
      <p class="workspaces-empty__title">{{ t('workspace.list.nothing_found') }}</p>
      <VBtn variant="text" size="small" @click="store.query = ''">
        {{ t('workspace.list.clear_search') }}
      </VBtn>
    </div>

    <EntityRowList
      v-else
      :items="store.visible"
      :reorderable="store.reorderable"
      :counters="counters"
      :labels="labels"
      @edit="edit"
      @remove="remove"
      @restore="(workspace) => store.restore(workspace.code)"
      @purge="purge"
      @move="store.move"
    />

    <WorkspaceFormDialog v-model="formOpen" :workspace="editing" @saved="store.load" />
    <WorkspaceDeleteDialog v-model="deleteOpen" :workspace="removing" @deleted="onDeleted" />
    <WorkspacePurgeDialog v-model="purgeOpen" :workspace="purging" @purged="store.load" />
  </PageLayout>
</template>

<style scoped>
.workspaces-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 8px;
  min-height: 200px;
  text-align: center;
}

.workspaces-empty__title {
  margin: 0;
  font-size: 15px;
  font-weight: 600;
  color: var(--text);
}

.workspaces-empty__hint {
  margin: 0 0 8px;
  font-size: 13px;
  color: var(--text-muted);
}
</style>
