<script setup lang="ts">
// Группы текущего пространства: список карточек, одно окно формы на создание и правку,
// подтверждение на каждое из двух удалений.
//
// Группа — долгоживущая тема внутри пространства («биллинг», «интерфейс»), по ней список задач
// разложен на секции. Отсюда и привязка: раздел показывает группы ТОГО пространства, что выбрано
// в боковой панели, и своего выбора пространств не заводит — второй такой выбор разошёлся бы с
// первым на первом же переключении.
//
// Удалённые лежат в том же списке под тумблером, а не на отдельной странице: они приезжают тем же
// запросом с флагом.
import { computed, onActivated, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  IconArchiveOff,
  IconDotsVertical,
  IconFlame,
  IconPencil,
  IconPlus,
  IconRefresh,
  IconTrash,
} from '@tabler/icons-vue'

import PageLayout from '@/layout/templates/PageLayout.vue'
import PageHeader from '@/layout/components/PageHeader.vue'
import ConfirmDialog from '@/components/ConfirmDialog.vue'
import SectionError from '@/components/SectionError.vue'
import { colorVarsByName } from '@/shared/colors'
import IconSwatch from '@/components/IconSwatch.vue'
import { fmtDateTime } from '@/shared/utils/date'

import GroupFormDialog from '../components/GroupFormDialog.vue'
import { deleteGroup, purgeGroup, type GroupListRow } from '../api'
import { useGroupsStore } from '../stores/groups.store'
import { useWorkspaceContextStore } from '@/features/workspace/stores/workspace-context.store'

const { t } = useI18n()
const store = useGroupsStore()
const context = useWorkspaceContextStore()

// Страница живёт в KeepAlive и между переходами не размонтируется: `onMounted` отрабатывает
// первый показ, `onActivated` — каждое возвращение, иначе список остался бы вчерашним.
onMounted(store.load)
onActivated(store.load)

const workspace = computed(() => context.currentWorkspace?.code ?? '')

const showDeleted = computed({
  get: () => store.includeDeleted,
  set: (value: boolean) => { store.showDeleted(value) },
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

// Оба удаления закрывают окно только на успехе: на отказе оно остаётся открытым, а сообщение
// показывает тост клиента — своего места под него у подтверждения нет.
async function remove() {
  const group = removing.value
  if (!group) return
  busy.value = true
  try {
    await deleteGroup(group.code)
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
        <VSwitch
          v-model="showDeleted"
          :label="t('tasks.group.list.show_deleted')"
          color="primary"
          density="compact"
          hide-details
          class="deleted-switch"
        />
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

    <!-- Пространств нет вовсе: группам негде лежать, и предлагать завести группу здесь значило бы
         вести в отказ. Ведём туда, где заводят пространство. -->
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

    <div v-else class="group-grid">
      <VCard
        v-for="group in store.items"
        :key="group.code"
        variant="flat"
        class="group-card color-tones"
        :class="{ 'group-card--deleted': group.deleted_at }"
        :style="colorVarsByName(group.color)"
      >
        <header class="group-card__header">
          <IconSwatch :icon="group.icon" :color="group.color" :width="34" />
          <h3 class="group-card__title">{{ group.title }}</h3>

          <VChip v-if="group.deleted_at" color="error" variant="tonal" size="x-small">
            {{ t('tasks.group.card.deleted') }}
          </VChip>

          <VMenu location="bottom end" :offset="4">
            <template #activator="{ props: menu }">
              <VBtn
                v-bind="menu"
                icon
                variant="text"
                class="group-card__action"
                :title="t('tasks.group.card.actions')"
              >
                <IconDotsVertical :size="16" :stroke-width="1.6" />
              </VBtn>
            </template>

            <!-- Набор действий зависит от состояния: у живой — правка и мягкое удаление, у
                 удалённой — возврат и снос. Править удалённую бэк не даёт (409), и показывать
                 пункт, который заведомо откажет, значит врать кнопкой. -->
            <VList density="compact">
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
                <VListItem :prepend-icon="IconArchiveOff" @click="store.restore(group.code)">
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
          <span class="group-card__count-label">{{ t('tasks.group.card.tasks') }}</span>
          <span class="group-card__sort">{{ t('tasks.group.card.sort') }}: {{ group.sort }}</span>
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

    <!-- Удаление группы не трогает её задачи, и об этом сказано прямо: иначе «внутри 12 задач»
         читается как предупреждение, что исчезнут и они. -->
    <ConfirmDialog
      v-model="deleteOpen"
      :title="t('tasks.group.delete.title')"
      :text="t('tasks.group.delete.text', { count: removing?.task_count ?? 0 })"
      :confirm-label="t('tasks.group.card.delete')"
      :loading="busy"
      @confirm="remove"
    />

    <ConfirmDialog
      v-model="purgeOpen"
      :title="t('tasks.group.purge.title')"
      :text="t('tasks.group.purge.text', { count: purging?.task_count ?? 0 })"
      :confirm-label="t('tasks.group.card.purge')"
      :loading="busy"
      @confirm="purge"
    />
  </PageLayout>
</template>

<style scoped>
/* Подпись тумблера приглушена, когда он выключен, — так же, как у пространств: полная
   насыщенность читалась бы как включённое состояние. */
.deleted-switch {
  flex: none;
  margin-right: 8px;
}

.deleted-switch :deep(.v-selection-control:not(.v-selection-control--dirty) .v-label) {
  opacity: var(--v-medium-emphasis-opacity);
}

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

/* Удалённое приглушено целиком, а не помечено одной меткой: карточка в корзине не должна
   соперничать за внимание с живыми в том же ряду. Наведение возвращает непрозрачность. */
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

/* Коробка задана здесь, а не пропсами `size`/`density`: у иконочной кнопки Vuetify считает
   сторону как `--v-btn-height + 12px`, а density правит только высоту. */
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

/* Описание фиксировано на две строки: короткие резервируют высоту, длинные обрезаются
   многоточием — карточки в ряду выравниваются по высоте. */
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

/* Подвал прижат к низу карточки — карточки в ряду выравниваются по нижней границе. */
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

.group-card__sort {
  margin-left: 8px;
  font-size: 11px;
  color: var(--text-faint);
}

.group-card__updated {
  margin-left: auto;
  font-size: 11px;
  color: var(--text-faint);
  white-space: nowrap;
}
</style>
