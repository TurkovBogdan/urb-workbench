<script setup lang="ts">
// Tasks of the current workspace: a dense list with a filter panel.
//
// The page itself draws nothing but the header: rows are shown by the FORMAT component, filters by
// their own panel. The format is stored as a value in the store, and its markup lives in a
// separate component (`FORMATS`): a second format (a board) should appear as one line in the table
// below plus a new file alongside, not as a branch in the middle of this markup.
//
// URL. The list lives at `/tasks/list`, a task on its own page (`/tasks/task/TASK@…`), and a click
// on a row navigates there. The filter set is not put into the URL: it is the person's working
// posture, and every letter typed into the search would write an entry to the browser history.
import { computed, onActivated, ref, watch, type Component } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { IconFolderPlus, IconList, IconPlus, IconRefresh } from '@tabler/icons-vue'

import PageLayout from '@/layout/templates/PageLayout.vue'
import PageHeader from '@/layout/components/PageHeader.vue'
import SectionError from '@/components/SectionError.vue'
import { useChangeSubscription } from '@/composables/useChangeSubscription'
import { useFindShortcut } from '@/composables/useFindShortcut'
import type { Change } from '@/stores/changes'

import GroupDeleteDialog from '../components/GroupDeleteDialog.vue'
import GroupFormDialog from '../components/GroupFormDialog.vue'
import TaskFilters from '../components/TaskFilters.vue'
import TaskFormDialog from '../components/TaskFormDialog.vue'
import TaskListTable from '../components/TaskListTable.vue'
import { useTasksStore } from '../stores/tasks.store'
import { useWorkspaceContextStore } from '@/features/workspace/stores/workspace-context.store'
import type { TaskListFormat } from '../stores/tasks.store'
import {
  deleteGroup,
  type GroupListRow,
  type GroupRow,
  type GroupTaskDisposal,
  type TaskDetail,
  type TaskListRow,
} from '../api'

const { t } = useI18n()
const route = useRoute()
const router = useRouter()
const store = useTasksStore()
const context = useWorkspaceContextStore()

// Display formats: store value → component and button label. All a second format takes is one
// line here plus the component itself; neither the header, the filters nor the task dialog will
// know about it.
const FORMATS: { code: TaskListFormat; label: string; icon: Component; view: Component }[] = [
  { code: 'list', label: 'tasks.task.list.format.list', icon: IconList, view: TaskListTable },
]

const formatView = computed(
  () => (FORMATS.find((item) => item.code === store.format) ?? FORMATS[0]).view,
)

// The page lives in KeepAlive and is not unmounted between navigations. `onActivated` fires both on
// first display and on every return, otherwise the list would stay stale; a second call from
// `onMounted` would send two identical requests in a row on first display.
onActivated(store.load)

const filtersEl = ref<HTMLElement | null>(null)
useFindShortcut(filtersEl)

const workspace = computed(() => context.currentWorkspace?.code ?? '')

// ── Live updates ──────────────────────────────────────────────────────────────
// The list re-reads itself from the change feed when someone else changes its tasks, their
// positions or groups. "Ours" is anything from the current workspace: a task and a group carry its
// code in `refs`, while a tree edge carries only task codes and is recognised by the ones already
// known. When to re-read is decided by the store (`reloadForChanges`): in the middle of its own
// gesture it postpones the re-read until the gesture ends.
function concernsList(change: Change): boolean {
  if (change.ids.length === 0) return true
  if (workspace.value && change.refs.includes(workspace.value)) return true
  const known = new Set([
    ...store.items.map((task) => task.code),
    ...store.groups.map((group) => group.code),
  ])
  return [...change.ids, ...change.refs].some((code) => known.has(code))
}

useChangeSubscription({
  entities: ['tasks.task', 'tasks.link', 'tasks.group'],
  match: concernsList,
  onChange: () => store.reloadForChanges(),
  onResync: () => store.reloadForChanges(),
  reloadsOnReturn: true,
})

// ── Navigating to a task ──────────────────────────────────────────────────────

function taskPath(code: string): string {
  return `/tasks/task/${encodeURIComponent(code)}`
}

// Where the person went from the list. The list sits in KeepAlive and comes back exactly as it was
// left — the mark on the row tells where the person came back from.
const lastOpened = ref<string | null>(null)

function openTask(code: string) {
  lastOpened.value = code
  void router.push(taskPath(code))
}

// A legacy of the modal dialog: a query parameter used to open the task, and such links have been
// shared. They are redirected to the page URL with a REPLACE — "back" from the task must lead to
// where the person followed the link from, not to the same list with a parameter that would
// redirect itself again.
watch(
  () => route.query.task,
  (value) => {
    if (typeof value !== 'string' || !value) return
    void router.replace(taskPath(value))
  },
  { immediate: true },
)

// ── Task form ─────────────────────────────────────────────────────────────────
// The dialog only creates: an existing task is edited on its page. There is one form for the whole
// page, wherever it is called from — the header, a group card or a row's "add subtask": a second copy would
// diverge from the first at the very first new field.
const parent = ref<TaskDetail | TaskListRow | null>(null)
// `undefined` — the form asks for the group; a code or `null` — it is decided by the card.
const presetGroup = ref<string | null | undefined>(undefined)
const formOpen = ref(false)

function create() {
  parent.value = null
  presetGroup.value = undefined
  formOpen.value = true
}

/** From a group card: the task starts in that group; `null` — the "No group" card. */
function createIn(group: string | null) {
  parent.value = null
  presetGroup.value = group
  formOpen.value = true
}

function addChild(task: TaskDetail | TaskListRow) {
  parent.value = task
  presetGroup.value = undefined
  formOpen.value = true
}

/**
 * Saving may have rearranged anything — group, status, body — so the list is re-read in full. A
 * newly created subtask opens right away: that is what it was created for.
 */
function onSaved(code: string) {
  void store.load()
  if (parent.value) openTask(code)
}

// ── Group form ────────────────────────────────────────────────────────────────
// The same dialog as on the groups page — editing is called from the card header in the list. It
// lives here, not inside the list: the page has one dialog per entity, and the display format (a
// board will be the second) must not carry them around.
const editingGroup = ref<GroupRow | null>(null)
const groupFormOpen = ref(false)

function createGroup() {
  editingGroup.value = null
  groupFormOpen.value = true
}

function editGroup(group: GroupRow) {
  editingGroup.value = group
  groupFormOpen.value = true
}

// ── Group deletion ────────────────────────────────────────────────────────────
// The groups page's dialog, for the same reason as the form. The task count comes from the group
// row, not from the rows on screen: the list may hide finished tasks or narrow them by filters, and
// the backend counts every live one.
const removingGroup = ref<GroupListRow | null>(null)
const groupDeleteOpen = ref(false)
const groupDeleting = ref(false)

function askRemoveGroup(group: GroupListRow) {
  removingGroup.value = group
  groupDeleteOpen.value = true
}

// Closes only on success: on refusal the dialog stays open and the client's toast says why.
async function removeGroup(fate: { tasks?: GroupTaskDisposal; target?: string }) {
  const group = removingGroup.value
  if (!group) return
  groupDeleting.value = true
  try {
    await deleteGroup(group.code, fate)
    groupDeleteOpen.value = false
    await store.load()
  } finally {
    groupDeleting.value = false
  }
}
</script>

<template>
  <PageLayout>
    <PageHeader
      :title="t('tasks.task.list.title')"
      :description="t('tasks.task.list.description')"
    >
      <template #actions>
        <!-- The display format is not a filter: it does not narrow the results but changes how
             they are drawn, so it belongs in the page header, not the filter panel. `mandatory` —
             the format cannot be unset, one is always on. While there is only one format there is
             nothing to choose, so there is no toggle — it will come back by itself with a second
             format in `FORMATS`. -->
        <VBtnToggle
          v-if="FORMATS.length > 1"
          v-model="store.format"
          mandatory
          density="comfortable"
          variant="outlined"
          divided
          class="format-toggle"
        >
          <VBtn v-for="item in FORMATS" :key="item.code" :value="item.code" icon>
            <component :is="item.icon" :size="18" />
            <VTooltip activator="parent" location="top">{{ t(item.label) }}</VTooltip>
          </VBtn>
        </VBtnToggle>

        <VBtn variant="text" :disabled="store.loading" @click="store.load">
          <template #prepend><IconRefresh :size="16" :class="{ 'icon-spin': store.loading }" /></template>
          {{ t('tasks.action.refresh') }}
        </VBtn>
        <VBtn variant="text" :disabled="!workspace" @click="createGroup">
          <template #prepend><IconFolderPlus :size="16" /></template>
          {{ t('tasks.group.list.add') }}
        </VBtn>
        <VBtn variant="text" :disabled="!workspace" @click="create">
          <template #prepend><IconPlus :size="16" /></template>
          {{ t('tasks.task.list.add') }}
        </VBtn>
      </template>
    </PageHeader>

    <SectionError v-if="store.error" :error="store.error" />

    <!-- No workspaces at all: tasks have nowhere to live, and neither the filters nor the table
         mean anything here — showing them with empty lists would offer to narrow down nothing.
         Point to where workspaces are created instead. -->
    <div v-else-if="store.noWorkspace" class="tasks-empty">
      <p class="tasks-empty__title">{{ t('tasks.task.list.no_workspace') }}</p>
      <p class="tasks-empty__hint">{{ t('tasks.task.list.no_workspace_hint') }}</p>
      <VBtn color="primary" variant="flat" to="/tasks/workspaces">
        {{ t('tasks.task.list.to_workspaces') }}
      </VBtn>
    </div>

    <!-- Search and filters are their own card ABOVE the list, one for all formats: they control
         what is shown and belong to the screen, not to whoever draws the rows (the same anatomy
         as other list pages — `FilterPanel` + a content card below it). -->
    <template v-else>
      <div ref="filtersEl" class="tasks-filters">
        <TaskFilters />
      </div>

      <component
        :is="formatView"
        :open-code="lastOpened"
        @open="openTask"
        @create="create"
        @create-in="createIn"
        @add-child="addChild"
        @edit-group="editGroup"
        @remove-group="askRemoveGroup"
      />
    </template>

    <TaskFormDialog
      v-model="formOpen"
      :workspace="workspace"
      :task="null"
      :parent="parent"
      :group="presetGroup"
      @saved="onSaved"
    />

    <!-- Editing a group changes both its card and the section layout, so the list is re-read in
         full — the same way as after editing a task. -->
    <GroupFormDialog
      v-model="groupFormOpen"
      :workspace="workspace"
      :group="editingGroup"
      @saved="store.load"
    />

    <GroupDeleteDialog
      v-model="groupDeleteOpen"
      :group="removingGroup"
      :groups="store.groups"
      :loading="groupDeleting"
      @confirm="removeGroup"
    />
  </PageLayout>
</template>

<style scoped>
/* The format group comes first in the action row and is set apart from it: it is about the page's
   view, while the neighbouring buttons are about its content. */
.format-toggle { margin-right: 4px; }

/* The filters stay in view while scrolling a long list — the same way the task page keeps its
   field column: what the list is narrowed by must be seen and changed from any row of it. The
   z-index lifts the block above the rows, which are positioned and would otherwise slide over it.
   On a phone the panel wraps into several lines, and a sticky block that tall would take the
   screen from the list itself.
   A wrapper sticks, not the card: stuck at `top: 0` the card would hang below the scroller's
   padding, and the rows would show through the strip above it. The wrapper sticks to the very
   edge (the padding cancelled, mirroring the layout's 24px / 16px fallbacks) and paints that
   strip in the page colour. Its own 16px top padding takes the place of the header's bottom
   margin, so at rest the card stands exactly where it did. The gap below the card is padding for
   the same reason: as a margin it would be transparent, and stuck the rows would run right up
   against the card instead of keeping the distance they have at rest. */
.tasks-filters {
  position: sticky;
  top: calc(-1 * var(--page-layout-pad, 24px));
  z-index: 2;
  margin-top: -16px;
  padding-block: 16px 12px;
  /* The gap below the card fades out instead of cutting the rows off at a hard edge. At rest the
     fade lies over empty page, so it shows only once the panel is stuck — no need to detect that. */
  background: linear-gradient(to bottom, var(--bg) calc(100% - 12px), transparent);
}

@media (max-width: 959px) {
  .tasks-filters { top: calc(-1 * var(--page-layout-pad, 16px)); }
}

@media (max-width: 600px) {
  .tasks-filters { position: static; }
}

.tasks-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 8px;
  min-height: 200px;
  text-align: center;
}

.tasks-empty__title {
  margin: 0;
  font-size: 15px;
  font-weight: 600;
  color: var(--text);
}

.tasks-empty__hint {
  margin: 0 0 8px;
  font-size: 13px;
  color: var(--text-muted);
}
</style>
