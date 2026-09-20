<script setup lang="ts">
// Панель фильтров списка задач: чем сузить выдачу и чем её вернуть обратно.
//
// Панель принадлежит СТРАНИЦЕ, а не формату показа: доска будет сужаться теми же ручками, что и
// список, и вторая их копия рядом разошлась бы с первой на первом же новом фильтре. Поэтому
// панель — отдельный компонент, а формат получает её слотом и только находит ей место (у списка —
// внутри его карточки над линейкой).
//
// ПОЛЕ, ЧИПЫ, КНОПКА. Пять постоянно раскрытых селектов стояли ровно там, куда падает первый
// взгляд, — над списком, — и занимали столько же места, сколько три строки задач. При этом
// заполнены они бывают редко: обычная поза — «всё» в каждом. Поэтому раскрыто только то, чем
// пользуются всегда (поиск), остальное сложено в панель, а НАБРАННОЕ показано чипами: видно
// ровно те фильтры, которые сейчас что-то делают, и каждый снимается на месте.
//
// Все значения живут в сторе списка, а не здесь: фильтры переживают уход со страницы и возврат на
// неё, и локальное состояние компонента сбрасывалось бы при каждом перемонтировании.
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { IconFilter, IconSearch } from '@tabler/icons-vue'

import { useTasksStore } from '../stores/tasks.store'
import { TASK_PRIORITIES, TASK_STATUSES, TASK_TYPES } from '../labels'

const { t } = useI18n()
const store = useTasksStore()

// «Без группы» в сторе — пустая строка (ровно так её понимает и бэк), но пустое значение внутри
// VSelect неотличимо от «ничего не выбрано»: поле перестало бы показывать выбранное и прятало бы
// крестик очистки. Наружу поле отдаёт свою метку, а стору достаётся пустая строка.
const UNASSIGNED = '@none'

const panelOpen = ref(false)

const statusItems = computed(() =>
  TASK_STATUSES.map((value) => ({ value, title: t(`tasks.task.status.${value}`) })),
)
const priorityItems = computed(() =>
  TASK_PRIORITIES.map((value) => ({ value, title: t(`tasks.task.priority.${value}`) })),
)
const typeItems = computed(() =>
  TASK_TYPES.map((value) => ({ value, title: t(`tasks.task.type.${value}`) })),
)
const groupItems = computed(() => [
  ...store.groups.map((group) => ({ value: group.code, title: group.title })),
  { value: UNASSIGNED, title: t('tasks.task.list.no_group') },
])

const query = computed({
  get: () => store.query,
  set: (value: string) => {
    store.query = value
    store.resetPage()
  },
})

const groupFilter = computed({
  get: () => (store.groupFilter === '' ? UNASSIGNED : store.groupFilter),
  set: (value: string | null) => {
    store.groupFilter = value === UNASSIGNED ? '' : value
    store.resetPage()
  },
})

/** Обычный фильтр-выбор: снятое значение (`null`) означает «все», и страница едет на первую. */
function pick(field: 'statusFilter' | 'priorityFilter' | 'typeFilter', value: string | null) {
  store[field] = value
  store.resetPage()
}

const showDeleted = computed({
  get: () => store.includeDeleted,
  set: (value: boolean) => { void store.showDeleted(value) },
})

// ── Набранное ────────────────────────────────────────────────────────────────

/** Снятый фильтр: `key` — по чему снимать, `label` — ЗНАЧЕНИЕ, а не «Статус: значение». */
interface FilterChip {
  key: 'status' | 'priority' | 'type' | 'group' | 'deleted'
  label: string
}

/** Название группы по коду; пустая строка — «Без группы», чужой код — сам код (группу могли убрать). */
function groupTitle(code: string): string {
  if (code === '') return t('tasks.task.list.no_group')
  return store.groups.find((group) => group.code === code)?.title ?? code
}

// Подпись у чипа — одно значение: «В работе», «Горит». Имя ручки («Статус») ничего не добавляет —
// значения по всем пяти не пересекаются, а с именами чипы вырастают вдвое и перестают быть
// пометками. Корзина стоит тут наравне с остальными: включённой её больше негде увидеть, а она
// меняет выдачу сильнее любого другого фильтра.
const chips = computed<FilterChip[]>(() => {
  const out: FilterChip[] = []
  if (store.statusFilter !== null)
    out.push({ key: 'status', label: t(`tasks.task.status.${store.statusFilter}`) })
  if (store.priorityFilter !== null)
    out.push({ key: 'priority', label: t(`tasks.task.priority.${store.priorityFilter}`) })
  if (store.typeFilter !== null)
    out.push({ key: 'type', label: t(`tasks.task.type.${store.typeFilter}`) })
  if (store.groupFilter !== null)
    out.push({ key: 'group', label: groupTitle(store.groupFilter) })
  if (store.includeDeleted)
    out.push({ key: 'deleted', label: t('tasks.task.list.show_deleted') })
  return out
})

function drop(chip: FilterChip) {
  switch (chip.key) {
    case 'status': return pick('statusFilter', null)
    case 'priority': return pick('priorityFilter', null)
    case 'type': return pick('typeFilter', null)
    case 'group': return void (groupFilter.value = null)
    case 'deleted': return void (showDeleted.value = false)
  }
}

/** «Сбросить всё» — только когда снимать есть что больше одного раза: иначе это тот же крестик. */
const showReset = computed(() => chips.value.length > 1)

function resetAll() {
  store.clearFilters()
  if (store.includeDeleted) showDeleted.value = false
}
</script>

<template>
  <div class="task-filters">
    <!-- Поле без рамки: рамка вокруг поиска рисует ещё одну коробку в карточке, у которой рамка
         уже есть. Сужает он по заголовку — тому единственному, что в строке читают глазами. -->
    <VTextField
      :model-value="query"
      :placeholder="t('tasks.task.filter.query')"
      :prepend-inner-icon="IconSearch"
      variant="plain"
      density="compact"
      hide-details
      clearable
      class="task-filters__search"
      @update:model-value="query = $event ?? ''"
    />

    <div class="task-filters__chips">
      <VChip
        v-for="chip in chips"
        :key="chip.key"
        size="small"
        variant="tonal"
        closable
        class="task-filters__chip"
        @click:close="drop(chip)"
      >
        {{ chip.label }}
      </VChip>

      <VBtn v-if="showReset" variant="text" size="small" class="task-filters__reset" @click="resetAll">
        {{ t('tasks.task.filter.reset') }}
      </VBtn>
    </div>

    <!-- Панель, а не ряд селектов: раскрытой она нужна раз в сеанс, а место занимала бы всегда.
         `close-on-content-click` снят — внутри выбирают несколько ручек подряд. -->
    <VMenu v-model="panelOpen" :close-on-content-click="false" location="bottom end" :offset="6">
      <template #activator="{ props: menu }">
        <VBtn
          v-bind="menu"
          variant="text"
          size="small"
          class="task-filters__button"
          :class="{ 'task-filters__button--on': chips.length > 0 }"
        >
          <template #prepend><IconFilter :size="16" :stroke-width="1.7" /></template>
          {{ t('tasks.task.filter.title') }}
        </VBtn>
      </template>

      <VCard class="task-filters__panel" variant="outlined" rounded="lg">
        <VSelect
          :model-value="store.statusFilter"
          :items="statusItems"
          :label="t('tasks.task.filter.status')"
          variant="outlined"
          density="comfortable"
          hide-details
          clearable
          @update:model-value="pick('statusFilter', $event)"
        />

        <VSelect
          :model-value="store.priorityFilter"
          :items="priorityItems"
          :label="t('tasks.task.filter.priority')"
          variant="outlined"
          density="comfortable"
          hide-details
          clearable
          @update:model-value="pick('priorityFilter', $event)"
        />

        <VSelect
          :model-value="store.typeFilter"
          :items="typeItems"
          :label="t('tasks.task.filter.type')"
          variant="outlined"
          density="comfortable"
          hide-details
          clearable
          @update:model-value="pick('typeFilter', $event)"
        />

        <VSelect
          v-model="groupFilter"
          :items="groupItems"
          :label="t('tasks.task.filter.group')"
          variant="outlined"
          density="comfortable"
          hide-details
          clearable
        />

        <!-- Корзина стоит последней и за линейкой: она не сужает выдачу, а расширяет её — и
             единственная из всех ручек стоит нового запроса к бэку (удалённых в обычном ответе
             нет вовсе). -->
        <VDivider />

        <VSwitch
          v-model="showDeleted"
          :label="t('tasks.task.list.show_deleted')"
          color="primary"
          density="compact"
          hide-details
          class="task-filters__deleted"
        />
      </VCard>
    </VMenu>
  </div>
</template>

<style scoped>
/* Панель живёт внутри карточки списка, поэтому отступ несёт она сама — те же 12px, что у фильтров
   реестра и у анатомии на витрине (/design-system/table-page); по вертикали меньше: в ряду
   осталось поле без рамки, а не поля с рамками. */
.task-filters {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 12px;
}

/* Поле не растягивается на всю строку: справа от него живут чипы набранного, и поиск, забравший
   себе всё свободное место, отжимал бы их к кнопке. 240px — порог, ниже которого подсказка в
   поле обрезается на полуслове. */
.task-filters__search {
  flex: 0 1 240px;
  min-width: 0;
}

.task-filters__search :deep(.v-field__input) { font-size: 13px; }
.task-filters__search :deep(.v-field__prepend-inner) { color: var(--text-faint); }

/* Чипы забирают остаток строки и переносятся: фильтров максимум пять, и в узком окне они уходят
   на вторую линию, а не выдавливают кнопку за край. */
.task-filters__chips {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
  flex: 1 1 auto;
  min-width: 0;
}

.task-filters__chip { font-size: 12px; }

.task-filters__reset { color: var(--text-muted); }

.task-filters__button { flex: none; color: var(--text-muted); }

/* Набранное подсвечивает саму кнопку: чипы могли уехать на вторую строку, и кнопка — второе
   место, где видно, что выдача сужена. */
.task-filters__button--on { color: var(--accent); }

/* Ручки в панели идут столбиком: в ряд их не выстроить — панель узкая, а подпись «Приоритет» в
   половинке поля нечитаема. */
.task-filters__panel {
  display: flex;
  flex-direction: column;
  gap: 10px;
  width: 260px;
  padding: 12px;
  background: var(--surface);
}

/* Подпись тумблера приглушена, когда он выключен, — как у остальных фильтров: полная
   насыщенность читалась бы как включённое состояние. */
.task-filters__deleted :deep(.v-selection-control:not(.v-selection-control--dirty) .v-label) {
  opacity: var(--v-medium-emphasis-opacity);
}
</style>
