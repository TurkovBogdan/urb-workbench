<script setup lang="ts">
// Groups of the current workspace: a list of cards, one form dialog for create and edit, a
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
import {
  IconCheck,
  IconCopy,
  IconDotsVertical,
  IconFlame,
  IconPencil,
  IconPlus,
  IconRefresh,
  IconRestore,
  IconTrash,
} from '@tabler/icons-vue'

import PageLayout from '@/layout/templates/PageLayout.vue'
import PageHeader from '@/layout/components/PageHeader.vue'
import ConfirmDialog from '@/components/ConfirmDialog.vue'
import SectionError from '@/components/SectionError.vue'
import { colorVarsByName } from '@/shared/colors'
import IconSwatch from '@/components/IconSwatch.vue'
import { fmtDateTime } from '@/shared/utils/date'
import { useChangeSubscription } from '@/composables/useChangeSubscription'
import { useClipboard } from '@/composables/useClipboard'
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
const { copy, isCopied } = useClipboard()

// The page lives in KeepAlive and is not unmounted between navigations. `onActivated` fires both on
// first display and on every return, otherwise the list would stay stale; a second call from
// `onMounted` would send two identical requests in a row on first display.
onActivated(store.load)

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
  onChange: () => void store.load(),
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
    <GroupFilters v-if="!store.noWorkspace" class="mb-3" />

    <!-- No workspaces at all: groups have nowhere to live, and offering to create a group here
         would lead into a refusal. Point to where workspaces are created instead. -->
    <div v-if="store.noWorkspace" class="groups-empty">
      <p class="groups-empty__title">{{ t('tasks.task.list.no_workspace') }}</p>
      <p class="groups-empty__hint">{{ t('tasks.task.list.no_workspace_hint') }}</p>
      <VBtn color="primary" variant="flat" to="/workspaces">
        {{ t('tasks.task.list.to_workspaces') }}
      </VBtn>
    </div>

    <div v-else-if="store.loading" class="group-grid">
      <VCard v-for="n in 3" :key="n" variant="flat" class="group-card skel-card">
        <VSkeletonLoader type="heading, text" />
      </VCard>
    </div>

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

    <!-- A live group's card opens its edit dialog — the same one as the menu item. A deleted one
         cannot be edited (409), so it is not clickable at all: it has no handler, and Vuetify does
         not render it as a link. -->
    <div v-else class="group-grid">
      <VCard
        v-for="group in store.visible"
        :key="group.code"
        variant="flat"
        class="group-card color-tones"
        :class="{ 'group-card--deleted': group.deleted_at }"
        :style="colorVarsByName(group.color)"
        v-on="group.deleted_at ? {} : { click: () => edit(group) }"
      >
        <header class="group-card__header">
          <IconSwatch :icon="group.icon" :color="group.color" :width="34" />
          <h3 class="group-card__title">{{ group.title }}</h3>

          <VChip v-if="group.deleted_at" color="error" variant="tonal" size="x-small">
            {{ t('tasks.group.card.deleted') }}
          </VChip>

          <!-- The code is how the group is named to the agent and in MCP, so copying is at hand,
               not only in the menu. `.stop` — copying must not also open the card's edit. -->
          <VBtn
            icon
            variant="text"
            class="group-card__action"
            :title="t('common.action.copy_code')"
            @click.stop="copy(group.code)"
          >
            <IconCheck v-if="isCopied(group.code)" :size="16" :stroke-width="1.6" />
            <IconCopy v-else :size="16" :stroke-width="1.6" />
          </VBtn>

          <VMenu location="bottom end" :offset="4">
            <template #activator="{ props: menu }">
              <VBtn
                v-bind="menu"
                icon
                variant="text"
                class="group-card__action"
                :title="t('tasks.group.card.actions')"
                @click.stop
              >
                <IconDotsVertical :size="16" :stroke-width="1.6" />
              </VBtn>
            </template>

            <!-- The action set depends on state: a live group gets edit and soft delete, a
                 deleted one gets restore and purge. The backend refuses to edit a deleted group
                 (409), and showing an item that is bound to fail would make the button lie. -->
            <VList density="compact">
              <!-- Copying the code does not depend on state: a deleted group keeps its code. -->
              <VListItem :prepend-icon="IconCopy" @click="copy(group.code)">
                <VListItemTitle>{{ t('common.action.copy_code') }}</VListItemTitle>
              </VListItem>
              <template v-if="!group.deleted_at">
                <VListItem :prepend-icon="IconPencil" @click="edit(group)">
                  <VListItemTitle>{{ t('tasks.group.card.edit') }}</VListItemTitle>
                </VListItem>
                <VListItem
                  :prepend-icon="IconTrash"
                  class="group-card__menu-danger"
                  @click="askRemove(group)"
                >
                  <VListItemTitle>{{ t('tasks.group.card.delete') }}</VListItemTitle>
                </VListItem>
              </template>
              <template v-else>
                <VListItem :prepend-icon="IconRestore" @click="store.restore(group.code)">
                  <VListItemTitle>{{ t('tasks.group.card.restore') }}</VListItemTitle>
                </VListItem>
                <VListItem
                  :prepend-icon="IconFlame"
                  class="group-card__menu-danger"
                  @click="askPurge(group)"
                >
                  <VListItemTitle>{{ t('tasks.group.card.purge') }}</VListItemTitle>
                </VListItem>
              </template>
            </VList>
          </VMenu>
        </header>

        <p class="group-card__desc">{{ group.description }}</p>

        <footer class="group-card__footer">
          <span class="group-card__count">{{ group.task_count }}</span>
          <span class="group-card__count-label">{{ t('tasks.group.card.tasks', group.task_count) }}</span>
          <span class="group-card__updated">
            {{ fmtDateTime(group.updated_at) }}
            <VTooltip activator="parent" location="top">
              {{ t('tasks.group.card.updated_at') }}
            </VTooltip>
          </span>
        </footer>
      </VCard>
    </div>

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

.group-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(340px, 1fr));
  gap: 12px;
}

.skel-card { min-height: 116px; }
.skel-card :deep(.v-skeleton-loader) { width: 100%; padding: 0; }

.group-card {
  display: flex;
  flex-direction: column;
  gap: 14px;
  padding: 18px;
}

/* A deleted card is muted as a whole, not just marked with a label: a card in the trash must not
   compete for attention with live ones in the same row. Hover restores the opacity. */
.group-card--deleted { opacity: 0.55; }
.group-card--deleted:hover { opacity: 1; }

.group-card__header {
  display: flex;
  align-items: center;
  gap: 10px;
}

.group-card__title {
  margin: 0;
  flex: 1;
  min-width: 0;
  font-size: 15px;
  font-weight: 600;
  line-height: 1.3;
  color: var(--text);
}

/* The box is set here, not via the `size`/`density` props: for an icon button Vuetify computes the
   side as `--v-btn-height + 12px`, and density only changes the height. */
.group-card__action {
  width: 26px;
  min-width: 26px;
  height: 26px;
  margin-right: -4px;
  color: var(--text-faint);
}

.group-card__action:hover { color: var(--text); }

.group-card__menu-danger :deep(.v-list-item-title) { color: var(--error); }
.group-card__menu-danger :deep(.v-list-item__prepend) { color: var(--error); }

/* The description is fixed at two lines: short ones reserve the height, long ones are cut with an
   ellipsis — cards in a row line up in height. */
.group-card__desc {
  margin: -6px 0 0;
  min-height: calc(1.5em * 2);
  font-size: 12px;
  line-height: 1.5;
  color: var(--text-muted);
  display: -webkit-box;
  -webkit-line-clamp: 2;
  line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

/* The footer is pinned to the card bottom — cards in a row line up along their bottom edge. */
.group-card__footer {
  display: flex;
  align-items: baseline;
  gap: 6px;
  border-top: 1px solid var(--border);
  padding-top: 12px;
  margin-top: auto;
}

.group-card__count {
  font-family: var(--font-mono);
  font-size: 18px;
  font-weight: 600;
  line-height: 1;
  color: var(--text);
}

.group-card__count-label {
  font-size: 11px;
  font-weight: 500;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--text-muted);
}

.group-card__updated {
  margin-left: auto;
  font-size: 11px;
  color: var(--text-faint);
  white-space: nowrap;
}
</style>
