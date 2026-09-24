<script setup lang="ts">
// Пространства: список карточек, одно окно формы на создание и правку, два окна удаления —
// обратимое и окончательное.
//
// Пространство — верхний уровень изоляции данных, общий для всех прикладных модулей. Что именно
// внутри, страница не знает: карточка показывает счётчики, которые объявили модули поверх
// (`counters` в строке списка). Без них «удалить» было бы предложением подтвердить неизвестное,
// а с перечислением зон и задач прямо здесь страница правилась бы на каждый новый модуль.
//
// Удалённые лежат в том же списке, а не на отдельной странице: они приезжают тем же запросом с
// флагом, и разводить их по адресам значило бы заводить второй список ради того же набора строк.
import { computed, onActivated, ref } from 'vue'
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
import SectionError from '@/components/SectionError.vue'
import { colorVarsByName } from '@/shared/colors'
import { iconByName } from '@/shared/icons'
import { fmtDateTime } from '@/shared/utils/date'

import WorkspaceFormDialog from '../components/WorkspaceFormDialog.vue'
import WorkspaceDeleteDialog from '../components/WorkspaceDeleteDialog.vue'
import WorkspacePurgeDialog from '../components/WorkspacePurgeDialog.vue'
import { useWorkspacesStore } from '../stores/workspaces.store'
import type { WorkspaceListRow } from '../api'

const { t } = useI18n()
const store = useWorkspacesStore()

// Страница живёт в KeepAlive и между переходами не размонтируется. `onActivated` срабатывает и на
// первый показ, и на каждое возвращение, иначе список остался бы вчерашним; второй вызов из
// `onMounted` дал бы при первом показе два одинаковых запроса подряд.
onActivated(store.load)

const showDeleted = computed({
  get: () => store.includeDeleted,
  set: (value: boolean) => { store.showDeleted(value) },
})

const editing = ref<WorkspaceListRow | null>(null)
const removing = ref<WorkspaceListRow | null>(null)
const purging = ref<WorkspaceListRow | null>(null)
const formOpen = ref(false)
const deleteOpen = ref(false)
const purgeOpen = ref(false)

// Создание и правка — одно окно: пустая карточка отличается от заполненной только тем, что
// пространства у неё пока нет.
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
        <!-- Тумблер стоит в шапке списка, а не в карточке фильтров: фильтров у списка нет, и
             карточка ради одного переключателя была бы рамкой вокруг пустоты. -->
        <VSwitch
          v-model="showDeleted"
          :label="t('workspace.list.show_deleted')"
          color="primary"
          density="compact"
          hide-details
          class="deleted-switch"
        />
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

    <div v-if="store.loading" class="workspace-grid">
      <VCard v-for="n in 3" :key="n" variant="flat" class="workspace-card skel-card">
        <VSkeletonLoader type="heading, text, text" />
      </VCard>
    </div>

    <SectionError v-else-if="store.error" :error="store.error" />

    <!-- Пустое состояние зовёт завести первое пространство: список, который ничего не предлагает,
         оставляет человека гадать, чего здесь не хватает. -->
    <div v-else-if="store.isEmpty" class="workspaces-empty">
      <p class="workspaces-empty__title">{{ t('workspace.list.empty') }}</p>
      <p class="workspaces-empty__hint">{{ t('workspace.list.empty_hint') }}</p>
      <VBtn color="primary" variant="flat" @click="create">
        <template #prepend><IconPlus :size="16" /></template>
        {{ t('workspace.list.add') }}
      </VBtn>
    </div>

    <div v-else class="workspace-grid">
      <!-- Цвет пространства живёт на самой карточке: от него красится плашка иконки. -->
      <VCard
        v-for="workspace in store.items"
        :key="workspace.code"
        variant="flat"
        class="workspace-card color-tones"
        :class="{ 'workspace-card--deleted': workspace.deleted_at }"
        :style="colorVarsByName(workspace.color)"
      >
        <header class="workspace-card__header">
          <span class="workspace-card__icon">
            <component :is="iconByName(workspace.icon)" :size="20" :stroke-width="1.6" />
          </span>
          <h3 class="workspace-card__title">{{ workspace.title }}</h3>

          <!-- Отметка удаления рядом с именем, а не в подвале: она меняет смысл всей карточки,
               и узнать о ней надо раньше, чем дойдёшь до счётчиков. -->
          <VChip v-if="workspace.deleted_at" color="error" variant="tonal" size="x-small">
            {{ t('workspace.card.deleted') }}
          </VChip>

          <VMenu location="bottom end" :offset="4">
            <template #activator="{ props: menu }">
              <VBtn
                v-bind="menu"
                icon
                variant="text"
                class="workspace-card__action"
                :title="t('workspace.card.actions')"
              >
                <IconDotsVertical :size="16" :stroke-width="1.6" />
              </VBtn>
            </template>

            <!-- Набор действий зависит от состояния: у живого — правка и мягкое удаление,
                 у удалённого — возврат и снос. Править удалённое бэк не даёт (409), и
                 показывать пункт, который заведомо откажет, значит врать кнопкой. -->
            <VList density="compact">
              <template v-if="!workspace.deleted_at">
                <VListItem :prepend-icon="IconPencil" @click="edit(workspace)">
                  <VListItemTitle>{{ t('workspace.card.edit') }}</VListItemTitle>
                </VListItem>
                <VListItem
                  :prepend-icon="IconTrash"
                  class="workspace-card__menu-danger"
                  @click="remove(workspace)"
                >
                  <VListItemTitle>{{ t('workspace.card.delete') }}</VListItemTitle>
                </VListItem>
              </template>
              <template v-else>
                <VListItem :prepend-icon="IconArchiveOff" @click="store.restore(workspace.code)">
                  <VListItemTitle>{{ t('workspace.card.restore') }}</VListItemTitle>
                </VListItem>
                <VListItem
                  :prepend-icon="IconFlame"
                  class="workspace-card__menu-danger"
                  @click="purge(workspace)"
                >
                  <VListItemTitle>{{ t('workspace.card.purge') }}</VListItemTitle>
                </VListItem>
              </template>
            </VList>
          </VMenu>
        </header>

        <p class="workspace-card__desc">{{ workspace.description }}</p>

        <!-- Слева — сколько внутри, справа — когда этого касались: два ответа об одном
             пространстве, но о разном, и по краям они читаются быстрее, чем в строку.
             Счётчики не перечислены здесь: их состав задают модули поверх, и карточка рисует
             то, что приехало, вместе с ключом подписи. Нет ни одного — подвал держит только
             дату, и это законное состояние установки без прикладных модулей. -->
        <footer class="workspace-card__footer">
          <template v-for="(counter, index) in workspace.counters" :key="counter.key">
            <span class="workspace-card__count" :class="{ 'workspace-card__count--next': index > 0 }">
              {{ counter.count }}
            </span>
            <span class="workspace-card__count-label">{{ t(counter.label_key) }}</span>
          </template>
          <span class="workspace-card__updated">
            {{ fmtDateTime(workspace.updated_at) }}
            <VTooltip activator="parent" location="top">
              {{ t('workspace.card.updated_at') }}
            </VTooltip>
          </span>
        </footer>
      </VCard>
    </div>

    <WorkspaceFormDialog v-model="formOpen" :workspace="editing" @saved="store.load" />
    <WorkspaceDeleteDialog v-model="deleteOpen" :workspace="removing" @deleted="store.load" />
    <WorkspacePurgeDialog v-model="purgeOpen" :workspace="purging" @purged="store.load" />
  </PageLayout>
</template>

<style scoped>
/* Подпись тумблера приглушена, когда он выключен, — так же, как у фильтров в реестрах: полная
   насыщенность читалась бы как включённое состояние. */
.deleted-switch {
  flex: none;
  margin-right: 8px;
}

.deleted-switch :deep(.v-selection-control:not(.v-selection-control--dirty) .v-label) {
  opacity: var(--v-medium-emphasis-opacity);
}

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

.workspace-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(340px, 1fr));
  gap: 12px;
}

.skel-card { min-height: 132px; }
.skel-card :deep(.v-skeleton-loader) { width: 100%; padding: 0; }

.workspace-card {
  display: flex;
  flex-direction: column;
  gap: 14px;
  padding: 18px;
}

/* Удалённое приглушено целиком, а не помечено одной меткой: карточка в корзине не должна
   соперничать за внимание с живыми, стоящими в том же ряду. Наведение возвращает
   непрозрачность — чтобы прочитать её, не приходится восстанавливать. */
.workspace-card--deleted {
  opacity: 0.55;
}

.workspace-card--deleted:hover {
  opacity: 1;
}

.workspace-card__header {
  display: flex;
  align-items: center;
  gap: 10px;
}

.workspace-card__icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 34px;
  height: 34px;
  border-radius: 8px;
  /* Цвет пространства, а без него — акцент приложения: тот же запасной путь, что у иконки. */
  color: var(--gc-ink, var(--accent));
  background: var(--gc-fill, var(--accent-soft));
  flex: none;
}

.workspace-card__title {
  font-size: 15px;
  font-weight: 600;
  color: var(--text);
  margin: 0;
  line-height: 1.3;
  flex: 1;
  min-width: 0;
}

/* Коробка задана здесь, а не пропсами `size`/`density`: у иконочной кнопки Vuetify считает
   сторону как `--v-btn-height + 12px`, а density правит только высоту. Незаслоённое правило
   перебивает `@layer vuetify-components` (см. docs/frontend/vuetify-css-patterns). */
.workspace-card__action {
  width: 26px;
  min-width: 26px;
  height: 26px;
  margin-right: -4px;
  color: var(--text-faint);
}

.workspace-card__action:hover { color: var(--text); }

.workspace-card__menu-danger :deep(.v-list-item-title) { color: var(--error); }
.workspace-card__menu-danger :deep(.v-list-item__prepend) { color: var(--error); }

/* Описание фиксировано на две строки: короткие резервируют высоту, длинные обрезаются
   многоточием — карточки в ряду выравниваются по высоте. */
.workspace-card__desc {
  font-size: 12px;
  color: var(--text-muted);
  line-height: 1.5;
  margin: -6px 0 0;
  min-height: calc(1.5em * 2);
  display: -webkit-box;
  -webkit-line-clamp: 2;
  line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

/* Подвал прижат к низу карточки — карточки в ряду выравниваются по нижней границе. */
.workspace-card__footer {
  display: flex;
  align-items: baseline;
  gap: 6px;
  border-top: 1px solid var(--border);
  padding-top: 12px;
  margin-top: auto;
}

.workspace-card__count {
  font-family: var(--font-mono);
  font-size: 18px;
  font-weight: 600;
  color: var(--text);
  line-height: 1;
}

/* Второй счётчик отбит от подписи первого сильнее, чем от своей: иначе «Зон 3 12 Задач»
   читается как одно число с хвостом. */
.workspace-card__count--next { margin-left: 8px; }

.workspace-card__count-label {
  font-size: 11px;
  font-weight: 500;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--text-muted);
}

.workspace-card__updated {
  margin-left: auto;
  font-size: 11px;
  color: var(--text-faint);
  white-space: nowrap;
}
</style>
