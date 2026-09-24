<script setup lang="ts">
// Подзадачи на странице задачи — тем же видом, что в общем списке.
//
// Одна карточка: сверху поиск и «показать сверх обычного», ниже ветка. Строки — те же `TaskRow`,
// контейнер — тот же `TaskSubtree`, что рисует ветку под задачей в списке: подзадача обязана
// выглядеть и двигаться одинаково, где бы её ни увидели. Корнем ветки здесь служит сама открытая
// задача, поэтому жесты те же, что внутри ветки списка: переставить среди сестёр можно, бросить в
// чужую ветку нельзя.
//
// Поиск превращает ветку в плоский ряд совпадений и выключает перестановку — как фильтр в
// списке: в ряду, где стоят не все сёстры, «встать после соседа» значит не то, что видно.
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
  /** Открытая задача — корень ветки. */
  taskCode: string
  workspace: string
  /** Задача в корзине: её ветка удалена вместе с ней и видна только вместе с удалёнными. */
  deleted: boolean
}>()

const emit = defineEmits<{
  open: [code: string]
  edit: [task: TaskListRow]
  addChild: [task: TaskListRow]
}>()

const { t } = useI18n()
const store = useTaskSubtreeStore()

// Источники — по отдельности, а не одним массивом: массив из геттера новый на каждое чтение, и
// перечитка карточки задачи (живое обновление) заново открывала бы ветку, хотя ни одно значение
// не поменялось.
watch(
  [() => props.taskCode, () => props.workspace, () => props.deleted],
  ([code, workspace, deleted]) => {
    if (code && workspace) void store.open(code, workspace, deleted)
  },
  { immediate: true },
)

// Ключи группы «показать сверх обычного» — те же две кнопки, что в панели фильтров списка.
const EXTRA_FINISHED = 'finished'
const EXTRA_DELETED = 'deleted'

/** Нажатая кнопка = показано; знак флагов стора разворачивается здесь, как в `TaskFilters`. */
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

// Ветка обновляется сама, когда задачи или их места меняет кто-то другой (агент, другая вкладка).
// Ветку строит плоский список пространства, поэтому «своё» — всё из этого пространства: новая
// задача несёт его в `refs`, а ребро дерева — только коды задач, и узнаётся по уже известным.
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
  <!-- Подзадач нет вовсе — нет и карточки: поиск и переключатели над пустотой обещают список,
       которого нет. Остаётся строка, как у пустого журнала. Пока ветка грузится, не показывается
       ничего: иначе у задачи с подзадачами на миг мелькало бы «подзадач нет». -->
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

      <!-- У задачи в корзине живых подзадач нет вовсе, и «Удалённые» у неё не выключить: без них
           ветка была бы пустой, хотя под задачей лежит всё, что вернётся вместе с ней. -->
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

    <!-- Совпадения поиска — плоским рядом без ручек: см. шапку файла. -->
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
/* Тот же вид, что у пустого журнала (`TaskJournal`, `.journal__empty`): соседние секции страницы
   говорят «пусто» одним голосом. */
.subtasks-empty {
  margin: 0;
  font-size: 13px;
  color: var(--text-muted);
}

/* Ряд ручек — как панель фильтров списка (`filter-panel` + `TaskFilters`): поиск слева,
   переключатели прижаты к правому краю, в узком окне переносятся целиком. */
.subtasks__toolbar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  padding: 10px 12px;
}

/* Колонка у страницы задачи уже списка: поиск отдаёт ширину первым, иначе переключатели уезжали
   на вторую строку, хотя места им хватало. */
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

/* Полоса обновления не раздвигает карточку: перечитка после каждого жеста дёргала бы строки. */
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

/* Разделители плоского ряда — те же, что у ветки (`TaskSubtree`): линия над каждой строкой, и
   над первой тоже — она же отделяет ряд от панели ручек. */
.subtasks__flat-item {
  border-top: 1px solid var(--border-soft);
}
</style>
