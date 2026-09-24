<script setup lang="ts">
// Панель фильтров списка задач: чем сузить выдачу и чем её вернуть обратно.
//
// Панель принадлежит СТРАНИЦЕ, а не формату показа: доска будет сужаться теми же ручками, что и
// список, и вторая их копия рядом разошлась бы с первой на первом же новом фильтре. Поэтому
// панель — отдельный компонент, а формат получает её слотом и только находит ей место (у списка —
// внутри его карточки над линейкой).
//
// ВСЁ НА ВИДУ. Ручки стоят в ряд, без кнопки, открывающей их списком: свёрнутая панель экономила
// место, но платила за это двумя движениями вместо одного.
//
// ДВЕ СТРОКИ, И ВТОРАЯ ПРИХОДИТ ЦЕЛИКОМ. Верхняя — ручки, она на месте всегда; нижняя — набранное
// и сброс, её нет, пока сужать нечем. Разделены они потому, что иначе появляющийся сброс двигал
// бы ручки с их мест на каждом выборе, а постоянная разметка не должна зависеть от того, набрано
// что-то или нет.
//
// ПОРЯДОК РЯДА: поиск, справочники, переключатели. Первым идёт поиск — им пользуются всегда, и он
// единственный, ради чего в панель смотрят, не собираясь ничего настраивать. Последней — группа
// «показать сверх обычного»: завершённое и удалённое список по умолчанию не показывает, и эти две
// кнопки РАСШИРЯЮТ выдачу, а не сужают её, поэтому и стоят отдельно от справочников, прижатые к
// правому краю.
//
// Все значения живут в сторе списка, а не здесь: фильтры переживают уход со страницы и возврат на
// неё, и локальное состояние компонента сбрасывалось бы при каждом перемонтировании.
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { IconCircleCheck, IconTrash } from '@tabler/icons-vue'

import SearchField from '@/components/SearchField.vue'

import { useTasksStore } from '../stores/tasks.store'
import { taskScopesModel, taskSearchScopes } from '../search'
import {
  TASK_PRIORITIES,
  TASK_STATUSES,
  priorityColor,
  priorityIcon,
  statusColor,
  statusIcon,
} from '../labels'

const { t } = useI18n()
const store = useTasksStore()

// В поле статуса подробно показан ПЕРВЫЙ выбранный, остальные — счётчиком: поле обязано остаться
// в одну строку, а два значения со значками в неё не помещаются ни при какой разумной ширине.
// Весь набор всё равно виден чипами под ручками.

// Ключи группы «показать сверх обычного» — она одна на два независимых переключателя.
const EXTRA_FINISHED = 'finished'
const EXTRA_DELETED = 'deleted'

const statusItems = computed(() =>
  TASK_STATUSES.map((value) => ({ value, title: t(`tasks.task.status.${value}`) })),
)
const priorityItems = computed(() =>
  TASK_PRIORITIES.map((value) => ({ value, title: t(`tasks.task.priority.${value}`) })),
)

const query = computed({
  get: () => store.query,
  set: (value: string) => {
    store.query = value
    store.resetPage()
  },
})

// Области глубины — набор ключей у поля и три флага в сторе; переходник живёт в `search.ts`.
const scopes = computed(() => taskSearchScopes((scope) => t(`tasks.task.filter.scope.${scope}`)))
const activeScopes = taskScopesModel(
  () => store.searchScopes,
  (next) => {
    store.searchScopes = next
    store.resetPage()
  },
)

const statusPicked = computed({
  get: () => store.statusFilter,
  set: (value: string[]) => {
    store.statusFilter = value
    store.resetPage()
  },
})

/** Приоритет выбирается по одному: снятое значение (`null`) означает «все», и страница едет на первую. */
function pickPriority(value: string | null) {
  store.priorityFilter = value
  store.resetPage()
}

/**
 * Группа «показать сверх обычного»: нажатая кнопка — показываем, отжатая — прячем.
 *
 * В сторе это два разных по знаку флага: `hideFinished` (умолчание — прятать) и `includeDeleted`
 * (умолчание — не спрашивать у бэка). Знак разворачивается здесь, потому что на экране обе
 * кнопки отвечают на один вопрос — «это сейчас показано?», — и кнопка «не прятать завершённые»
 * читалась бы задом наперёд.
 */
const extras = computed({
  get: () => [
    ...(store.hideFinished ? [] : [EXTRA_FINISHED]),
    ...(store.includeDeleted ? [EXTRA_DELETED] : []),
  ],
  set: (keys: string[]) => {
    store.hideFinished = !keys.includes(EXTRA_FINISHED)
    store.resetPage()
    // Корзина — единственная ручка, которая стоит нового запроса: удалённых в обычном ответе нет
    // вовсе, и показать их нечем, кроме как спросив бэк заново.
    const deleted = keys.includes(EXTRA_DELETED)
    if (deleted !== store.includeDeleted) void store.showDeleted(deleted)
  },
})

/** «Сбросить» — когда есть что сбрасывать: набранный фильтр или снятое умолчание. */
const showReset = computed(
  () => store.hasActiveFilters || store.includeDeleted || !store.hideFinished,
)

function resetAll() {
  store.clearFilters()
  if (store.includeDeleted) void store.showDeleted(false)
}

// ── Набранное ────────────────────────────────────────────────────────────────

/**
 * Снятое значение: `key` — по чему снимать, `label` — САМО значение, а не «Статус: значение».
 *
 * Строка набранного отвечает на один вопрос — «чем сейчас сужено» — и отвечает на него в одном
 * месте, а не по нескольким полям, в каждое из которых надо посмотреть отдельно. Значения статуса
 * стоят в ней по одному: их выбирают набором, и снимать их приходится тоже по одному.
 *
 * Завершённых и удалённых здесь нет: их состояние показывают сами кнопки, и третья копия того же
 * факта говорила бы ровно то, что уже сказано.
 */
interface FilterChip {
  key: string
  label: string
  status?: string
}

const chips = computed<FilterChip[]>(() => {
  const out: FilterChip[] = []
  for (const status of store.statusFilter)
    out.push({ key: `status:${status}`, status, label: t(`tasks.task.status.${status}`) })
  if (store.priorityFilter !== null)
    out.push({ key: 'priority', label: t(`tasks.task.priority.${store.priorityFilter}`) })
  return out
})

function drop(chip: FilterChip) {
  if (chip.status)
    return void (statusPicked.value = store.statusFilter.filter((value) => value !== chip.status))
  if (chip.key === 'priority') pickPriority(null)
}
</script>

<template>
  <div class="task-filters">
    <div class="task-filters__row">
      <SearchField
        v-model="query"
        v-model:active-scopes="activeScopes"
        :scopes="scopes"
        :placeholder="t('tasks.task.filter.query')"
        density="compact"
        class="task-filters__search"
      />

      <!-- Статус выбирается набором: «в работе и на проверке» — обычная поза, а одно значение за
           раз заставляло бы смотреть список дважды. Значок тот же, что в строке списка и в поле
           статуса на деталке: один статус не может выглядеть по-разному в трёх местах. -->
      <VSelect
        v-model="statusPicked"
        :items="statusItems"
        :label="t('tasks.task.filter.status')"
        variant="outlined"
        density="compact"
        hide-details
        clearable
        multiple
        :chips="false"
        class="task-filters__pick task-filters__pick--status"
      >
        <template #item="{ props: itemProps, item }">
          <VListItem v-bind="itemProps">
            <template #prepend="{ isSelected }">
              <VCheckboxBtn :model-value="isSelected" density="compact" />
              <span class="task-filters__glyph" :class="`task-filters__glyph--${statusColor(item.value)}`">
                <component :is="statusIcon(item.value)" :size="16" :stroke-width="1.6" />
              </span>
            </template>
          </VListItem>
        </template>

        <!-- Выбранное показано значками с подписями, а за порогом — счётчиком: весь набор в поле
             не помещается, и обрезанный на полуслове он не читается вовсе. `:chips="false"` здесь
             обязателен: приложение включает чипы всем VSelect разом (`plugins/vuetify.ts`), а с
             ними Vuetify рисует `#chip` и молча игнорирует этот слот — та же ловушка, что у поля
             статуса на деталке. -->
        <template #selection="{ item, index }">
          <span v-if="index === 0" class="task-filters__picked">
            <span class="task-filters__glyph" :class="`task-filters__glyph--${statusColor(item.value)}`">
              <component :is="statusIcon(item.value)" :size="14" :stroke-width="1.6" />
            </span>
            <!-- Подпись отдельным элементом: многоточие работает на своём блоке, а не на строке
                 flex-контейнера, где рядом стоит значок. -->
            <span class="task-filters__picked-text">{{ item.title }}</span>
            <!-- Счётчик живёт ВНУТРИ первого выбранного, а не отдельным значением: Vuetify кладёт
                 каждое в свою обёртку, и вторая обрезалась бы вместе с подписью — «ещё» без числа
                 не говорит ничего. Здесь он сосед подписи и сжимается последним. -->
            <span v-if="store.statusFilter.length > 1" class="task-filters__more">
              {{ t('tasks.task.filter.status_more', { count: store.statusFilter.length - 1 }) }}
            </span>
          </span>
        </template>
      </VSelect>

      <!-- `:chips="false"` по той же причине, что и у статуса: приложение включает чипы
           каждому VSelect (`plugins/vuetify.ts`), а чип в поле не сжимается и не умеет многоточия.
           Значение фильтра и не должно быть чипом: чипы стоят строкой ниже, и в поле они были бы
           их же копией.
           Приоритет узнаётся по тому же глифу, что в строке списка и в поле приоритета на деталке, —
           и в пунктах, и в выбранном значении. -->
      <VSelect
        :model-value="store.priorityFilter"
        :items="priorityItems"
        :label="t('tasks.task.filter.priority')"
        variant="outlined"
        density="compact"
        hide-details
        clearable
        :chips="false"
        class="task-filters__pick"
        @update:model-value="pickPriority"
      >
        <template #item="{ props: itemProps, item }">
          <VListItem v-bind="itemProps">
            <template #prepend>
              <span class="task-filters__glyph" :class="`task-filters__glyph--${priorityColor(item.value)}`">
                <component :is="priorityIcon(item.value)" :size="16" :stroke-width="1.6" />
              </span>
            </template>
          </VListItem>
        </template>

        <template #selection="{ item }">
          <span class="task-filters__picked">
            <span class="task-filters__glyph" :class="`task-filters__glyph--${priorityColor(item.value)}`">
              <component :is="priorityIcon(item.value)" :size="14" :stroke-width="1.6" />
            </span>
            <span class="task-filters__picked-text">{{ item.title }}</span>
          </span>
        </template>
      </VSelect>

      <!-- Нажатая кнопка = показано. Группой, а не двумя отдельными тумблерами: обе отвечают на
           один вопрос «что ещё показать», и врозь они читались бы как два независимых фильтра. -->
      <VBtnToggle
        v-model="extras"
        multiple
        variant="outlined"
        divided
        density="compact"
        color="primary"
        class="task-filters__extras"
      >
        <VBtn :value="EXTRA_FINISHED" size="small">
          <template #prepend><IconCircleCheck :size="16" :stroke-width="1.7" /></template>
          {{ t('tasks.task.filter.finished') }}
        </VBtn>
        <VBtn :value="EXTRA_DELETED" size="small">
          <template #prepend><IconTrash :size="16" :stroke-width="1.7" /></template>
          {{ t('tasks.task.filter.deleted') }}
        </VBtn>
      </VBtnToggle>
    </div>

    <!-- Набранное и сброс — ОТДЕЛЬНАЯ строка, появляющаяся только когда есть что показать. В ряду
         с ручками сброс отжимал их с места каждый раз, когда человек что-то выбирал: постоянная
         разметка не должна зависеть от того, набрано что-то или нет. Здесь же строка приходит
         целиком и целиком уходит, ничего не сдвигая. -->
    <div v-if="chips.length || showReset" class="task-filters__applied">
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
  </div>
</template>

<style scoped>
/* Отступ панели несёт карточка, в которой она стоит (`filter-panel` на странице списка), — свой
   она не добавляет: два отступа подряд давали слева 24px, вдвое больше, чем у всего остального
   на странице. */
.task-filters {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

/* Ряд ручек переносится: в узком окне они уходят на следующую строку целиком, а не отжимают
   поиск к краю. */
.task-filters__row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
}

/* Набранное — своя строка под ручками, с той же сеткой: чипов может быть много (статусы идут по
   одному), и в узком окне они переносятся, а не выдавливают сброс за край. */
.task-filters__applied {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
}

/* Чип — пометка, а не заголовок: обычное начертание. Полужирным он читался бы наравне с именами
   задач в списке под ним и отбирал бы у них первый взгляд. */
.task-filters__chip {
  font-size: 12px;
  font-weight: 400;
}

/* Поиск шире остальных ручек и заметно: он не равноправный сосед справочников, а то, чем в этой
   панели пользуются каждый раз. Ниже 300px сжиматься не должен — там обрезается подсказка, и поле
   перестаёт объяснять, что оно ищет.
   Ручки НЕ растягиваются (`flex-grow: 0`) — иначе они делят между собой весь остаток строки, и
   группа переключателей уезжает на вторую, хотя места хватало. Сжиматься они могут: сначала до
   своих минимумов, а дальше ряд переносится. */
.task-filters__search {
  flex: 0 1 364px;
  min-width: 300px;
}

.task-filters__search :deep(.v-field__input) { font-size: 13px; }
.task-filters__search :deep(.v-field__prepend-inner) { color: var(--text-faint); }

/* Справочники уже поиска и сжимаются раньше него: 140px — ширина, на которой и подпись
   («Приоритет»), и выбранное значение со значком («Замороженный») читаются целиком. */
.task-filters__pick {
  flex: 0 1 164px;
  min-width: 140px;
}

/* ПОЛЕ ВСЕГДА В ОДНУ СТРОКУ. Ванильный VSelect переносит выбранное на вторую строку и растит
   поле в высоту — ряд ручек от этого разъезжается по вертикали, и соседние поля перестают
   стоять на одной линии. Длинное значение обрезается многоточием: обрезанное на полуслове
   «Неразобра» не читается, а «Неразобранные…» — читается. */
.task-filters__pick :deep(.v-field__input) {
  font-size: 13px;
  flex-wrap: nowrap;
  overflow: hidden;
}

.task-filters__pick :deep(.v-select__selection) {
  min-width: 0;
  overflow: hidden;
}

.task-filters__pick :deep(.v-select__selection-text) {
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
}

/* У статуса в поле стоит значение со значком плюс счётчик остальных: ему нужно шире соседей с
   одним значением. */
.task-filters__pick--status { flex: 0 1 200px; min-width: 176px; }

/* Группа прижата к правому краю и на перенесённой строке: место у «показать сверх обычного»
   постоянное, иначе её пришлось бы искать заново при каждом изменении набранного. */
.task-filters__extras {
  flex: none;
  margin-inline-start: auto;
}

.task-filters__extras :deep(.v-btn) { font-size: 12px; }

/* Сброс стоит В КОНЦЕ строки набранного, а не у правого края панели: он относится к чипам слева
   от него, и отъехав к краю читался бы как ручка, не связанная ни с чем. */
.task-filters__reset {
  flex: none;
  color: var(--text-muted);
}

/* Выбранный статус в поле: значок и подпись одной строкой. Длинная подпись сжимается и уходит в
   многоточие, но счётчик за ней не теряется — он говорит, что выбрано не только это. */
.task-filters__picked {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  min-width: 0;
  margin-inline-end: 6px;
  font-size: 13px;
}

.task-filters__picked-text {
  min-width: 0;
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
}

.task-filters__more {
  flex: none;
  font-size: 12px;
  color: var(--text-faint);
}

/* Цвета те же, что у глифа в строке списка и в поле статуса на деталке. */
.task-filters__glyph {
  display: inline-flex;
  align-items: center;
  flex: none;
}

.task-filters__glyph--accent  { color: var(--accent); }
.task-filters__glyph--success { color: var(--success); }
.task-filters__glyph--error   { color: var(--error); }
.task-filters__glyph--warn    { color: var(--warn); }
.task-filters__glyph--muted   { color: var(--text-faint); }
</style>
