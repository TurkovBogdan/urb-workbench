<script setup lang="ts">
// The codex section — every codex, and how each stands in the current workspace.
//
// TEST IMPLEMENTATION (TASK@8EAB179834): the first working cut to try the scheme on; the look and
// the words are still to be settled.
//
// Codexes are global: created, renamed and deleted here regardless of the workspace. Mounting is
// the workspace's: the switch in a row puts the codex into the current workspace's canvas — the one
// the agent reads as its development rules — and the editor shows exactly that canvas. A codex not
// mounted here is edited here (its name and line), not in the editor: write in what you work in.
import { computed, onActivated, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { IconBook2, IconPencil, IconPlus, IconRefresh, IconRestore, IconTrash } from '@tabler/icons-vue'

import PageLayout from '@/layout/templates/PageLayout.vue'
import PageHeader from '@/layout/components/PageHeader.vue'
import type { ActionMenuItem } from '@/components/ActionMenu.vue'
import ConfirmDialog from '@/components/ConfirmDialog.vue'
import EntityRowList, { type EntityRowLabels } from '@/components/EntityRowList.vue'
import SectionError from '@/components/SectionError.vue'
import { errorText } from '@/api/errorText'
import { pushToast } from '@/composables/useToasts'
import { useChangeSubscription } from '@/composables/useChangeSubscription'

import CodexEntryDialog from '../components/CodexEntryDialog.vue'
import CodexFilters from '../components/CodexFilters.vue'
import CodexRowSettings from '../components/CodexRowSettings.vue'
import { codexNodePath, displayPath } from '../paths'
import { useCodexListStore, type CodexListItem } from '../stores/codex-list.store'

const { t } = useI18n()
const router = useRouter()
const store = useCodexListStore()

onActivated(store.load)
// A codex created or mounted elsewhere — another tab, or the person's own MCP-driven agent.
useChangeSubscription({
  entities: ['codex.codex', 'codex.mount'],
  match: () => true,
  onChange: () => { void store.load() },
  onResync: () => { void store.load() },
  reloadsOnReturn: true,
})
// Another workspace picked in the sidebar: the mounts are its, the codexes stay.
watch(() => store.workspace, () => { void store.load() })
watch(() => store.showDeleted, () => { void store.load() })

// The row's own words. `updatedAt` and `purge` are not drawn: the middle is the codex's settings,
// and a deleted codex is only restored here — it is never purged from the list.
const labels = computed<EntityRowLabels>(() => ({
  drag: t('codex.list.drag'),
  deleted: t('codex.list.deleted'),
  actions: t('codex.list.actions'),
  updatedAt: '',
  edit: t('codex.list.edit'),
  delete: t('codex.list.delete'),
  restore: t('codex.list.restore'),
  purge: '',
}))

function menu(item: CodexListItem): ActionMenuItem[] {
  if (item.deleted_at) {
    return [{ key: 'restore', icon: IconRestore, label: t('codex.list.restore'), run: () => act(() => store.restore(item.code)) }]
  }
  return [
    { key: 'open', icon: IconBook2, label: t('codex.list.open'), hotkey: 'O', run: () => openEditor(item) },
    { key: 'edit', icon: IconPencil, label: t('codex.list.edit'), hotkey: 'E', run: () => edit(item) },
    { key: 'delete', icon: IconTrash, label: t('codex.list.delete'), danger: true, hotkey: 'D', run: () => askRemove(item) },
  ]
}

// Not available here: a grey, recessed plate — drawn by this page, below.
const rowClass = (item: CodexListItem) => ({ 'codex-row--off': !item.mounted })

const formOpen = ref(false)
const editing = ref<CodexListItem | null>(null)
const removing = ref<CodexListItem | null>(null)
const removeOpen = ref(false)

function create() {
  editing.value = null
  formOpen.value = true
}

function edit(item: CodexListItem) {
  editing.value = item
  formOpen.value = true
}

function askRemove(item: CodexListItem) {
  removing.value = item
  removeOpen.value = true
}

async function act(run: () => Promise<void>) {
  try {
    await run()
  } catch (e) {
    pushToast(errorText(e), 'error')
  }
}

async function confirmRemove() {
  const item = removing.value
  removeOpen.value = false
  if (item) await act(() => store.remove(item.code))
}

const mountAsk = ref<CodexListItem | null>(null)
const mountAskOpen = ref(false)

function goTo(code: string) {
  void router.push(codexNodePath(code))
}

// The editor shows the current workspace's canvas, so a codex not mounted here is offered to be
// mounted first — one click instead of a refusal on the next page.
function openEditor(item: CodexListItem) {
  if (item.mounted) {
    goTo(item.code)
    return
  }
  if (!store.workspace) {
    pushToast(t('codex.list.no_workspace'), 'error')
    return
  }
  mountAsk.value = item
  mountAskOpen.value = true
}

async function mountAndOpen() {
  const item = mountAsk.value
  mountAskOpen.value = false
  if (!item) return
  try {
    await store.setMounted(item.code, true)
    goTo(item.code)
  } catch (e) {
    pushToast(errorText(e), 'error')
  }
}

// A new codex is mounted at once and opened: it is created to be filled, and filling happens in the
// editor, on the canvas of the workspace you are in.
async function onCreated(row: { code: string }) {
  if (!editing.value && store.workspace) {
    await act(() => store.setMounted(row.code, true))
    goTo(row.code)
    return
  }
  await store.load()
}
</script>

<template>
  <PageLayout>
    <PageHeader :title="t('codex.list.title')" :description="t('codex.list.description')">
      <template #actions>
        <VBtn variant="text" :disabled="store.loading" @click="store.load">
          <template #prepend><IconRefresh :size="16" :class="{ 'icon-spin': store.loading }" /></template>
          {{ t('common.action.refresh') }}
        </VBtn>
        <VBtn color="primary" variant="flat" @click="create">
          <template #prepend><IconPlus :size="16" /></template>
          {{ t('codex.list.add') }}
        </VBtn>
      </template>
    </PageHeader>

    <!-- Search and filters stay in view while scrolling — the task list's sticky toolbar. -->
    <div class="codex-filters">
      <CodexFilters />
    </div>

    <SectionError v-if="store.error" :error="store.error" />

    <div v-else-if="!store.loading && !store.items.length" class="codex-empty">
      <p>{{ t('codex.list.empty') }}</p>
      <VBtn color="primary" variant="flat" @click="create">{{ t('codex.list.add') }}</VBtn>
    </div>

    <!-- Codexes exist but the filters left none: the way out is clearing them, not creating. -->
    <div v-else-if="!store.loading && !store.visible.length" class="codex-empty">
      <p>{{ t('codex.list.nothing_found') }}</p>
    </div>

    <!-- The groups' and workspaces' row: a click opens the edit dialog, as there; the materials are
         reached from the menu. The middle holds the settings in this workspace. -->
    <EntityRowList
      v-else
      :items="store.visible"
      :reorderable="store.reorderable"
      :labels="labels"
      :menu="menu"
      :row-class="rowClass"
      :fallback-icon="IconBook2"
      @edit="edit"
      @move="(code, index) => act(() => store.move(code, index))"
    >
      <template #title-extra="{ item }">
        <span class="codex-row__segment">{{ displayPath(item.segment) }}</span>
      </template>
      <template #columns="{ item }">
        <CodexRowSettings
          :item="item"
          :can-mount="Boolean(store.workspace)"
          @mount="(on) => act(() => store.setMounted(item.code, on))"
          @lock="(value) => act(() => store.setLock(item.code, value))"
        />
      </template>
    </EntityRowList>

    <CodexEntryDialog v-model="formOpen" :codex="editing" @saved="onCreated" />
    <ConfirmDialog
      v-model="mountAskOpen"
      :title="t('codex.list.mount_title')"
      :text="t('codex.list.mount_text', { title: mountAsk?.title ?? '' })"
      :confirm-label="t('codex.list.mount_confirm')"
      tone="primary"
      @confirm="mountAndOpen"
    />
    <ConfirmDialog
      v-model="removeOpen"
      :title="t('codex.list.delete_title')"
      :text="t('codex.list.delete_text', { title: removing?.title ?? '' })"
      :confirm-label="t('codex.list.delete')"
      @confirm="confirmRemove"
    />
  </PageLayout>
</template>

<style scoped>
/* The task list's sticky toolbar (`TasksView.vue` explains every line): the wrapper sticks to the
   scroller's very edge and paints the strip above the card in the page colour, the gap below fades
   out over the rows. On a phone the panel wraps tall, and stays put instead. */
.codex-filters {
  position: sticky;
  top: calc(-1 * var(--page-layout-pad, 24px));
  z-index: 2;
  margin-top: -16px;
  padding-block: 16px 12px;
  background: linear-gradient(to bottom, var(--bg) calc(100% - 12px), transparent);
}

@media (max-width: 959px) {
  .codex-filters { top: calc(-1 * var(--page-layout-pad, 16px)); }
}

@media (max-width: 600px) {
  .codex-filters { position: static; }
}

/* Plain soft text, not a badge: the code is a secondary name beside the title. */
.codex-row__segment {
  flex: none;
  font-size: 12px;
  color: var(--text-faint);
}

/* Not available here: a grey, recessed plate — still fully readable, just set aside from this
   workspace's canvas. Opaque on purpose: a see-through row reads as disabled, and its controls
   are not. The badge goes grey with it. */
:deep(.entity-row.codex-row--off) {
  background: var(--surface-sunken);
  border-color: var(--border-sunken);
}

:deep(.codex-row--off .entity-row__icon) {
  color: var(--text-faint);
  background: var(--surface);
}

:deep(.codex-row--off .v-divider) { border-color: var(--border-sunken); }

.codex-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  min-height: 200px;
  justify-content: center;
  color: var(--text-muted);
}
</style>
