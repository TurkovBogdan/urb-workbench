<script setup lang="ts">
// Одна строка списка задач: состояние, важность, название, служебные пометки, меню.
//
// Отдельным компонентом, потому что строк в ветке две породы — корень и подзадача, — и живут они
// в разных контейнерах: у каждого контейнера свой sortable (см. `TaskRows` и `TaskSubtree`).
// Сама строка про это ничего не знает: ей передают, что она умеет, и она это показывает.
//
// РАЗМЕТКА — НЕ ТАБЛИЦА. Строка читается слева направо как фраза: состояние, важность, название,
// пометки. Метка, которой у задачи нет, просто отсутствует — вместо прочерка в ячейке.
//
// ТИШЕ ЗАГОЛОВКА. В трекере строку ищут глазами по названию, всё остальное — пометки, и они
// обязаны быть тише текста. Отсюда правило на весь файл: цвет несут только состояние и
// срочность, остальное — глиф и приглушённые 12px. Цветных слов и тональных плашек в строке нет
// вовсе: шильдик со словом «В тестировании» читается наравне с заголовком и отбирает у него
// первый взгляд.
//
// Ровно 36px: в списке ищут сверху вниз, а разноэтажные строки приходится разглядывать. Поэтому
// ни описания, ни тела здесь нет — за ними открывают задачу.
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  IconArchiveOff,
  IconArrowDown,
  IconArrowUp,
  IconDotsVertical,
  IconPencil,
  IconSubtask,
  IconTrash,
  IconUnlink,
} from '@tabler/icons-vue'

import CounterButton from '@/components/CounterButton.vue'
import DragHandle from '@/components/DragHandle.vue'
import { fmtDate, fmtDateShort } from '@/shared/utils/date'

import { isTerminal, priorityColor, priorityIcon, statusColor, statusIcon } from '../labels'
import { useTasksStore } from '../stores/tasks.store'
import type { TaskListRow } from '../api'

const props = defineProps<{
  task: TaskListRow
  /** Ноль — корень ветки, дальше подзадачи: по глубине считается отступ и направляющая. */
  depth: number
  /** Последняя среди сестёр — загиб направляющей вместо сквозной линии. */
  last: boolean
  /** Сколько под ней подзадач; ноль — пометки нет. */
  childCount: number
  /** Это та задача, на которую уходили со списка. */
  open?: boolean
  /** Порядок в этой выдаче можно менять: показывать ручку и пункты перестановки. */
  reorderable?: boolean
  /** Есть куда шагнуть вверх / вниз среди сестёр; считает контейнер — он и знает ряд. */
  canUp?: boolean
  canDown?: boolean
  /**
   * Под строкой нарисована ветка, и её можно свернуть. Решает контейнер: он знает, есть ли у
   * задачи видимые дети, — на сужённой выдаче веток нет вовсе, и стрелки тоже.
   */
  foldable?: boolean
}>()

const emit = defineEmits<{
  open: [code: string]
  edit: [task: TaskListRow]
  addChild: [task: TaskListRow]
  remove: [code: string]
  restore: [code: string]
  /** Шаг по ряду сестёр без мыши. */
  step: [direction: -1 | 1]
  /** Открепить от родителя: подзадача становится обычной задачей. */
  detach: []
}>()

const { t } = useI18n()
const store = useTasksStore()

// Свёрнутость ветки живёт в сторе рядом со свёрнутостью карточек групп — одна карта на обе:
// коды задач и групп не пересекаются. Умолчание у задачи — раскрыта.
const folded = computed(() => store.isCollapsed(props.task.code))

/** Работа закрыта или задача в корзине — строка уходит в приглушённый тон. */
function dimmed(task: TaskListRow): boolean {
  return isTerminal(task.status) || task.deleted_at !== null
}

/**
 * Срок прошёл, а работа не закрыта. Красим только этот случай: все сроки подряд в
 * предупреждающем цвете кричали бы обо всех задачах разом и потому ни об одной.
 */
function overdue(task: TaskListRow): boolean {
  if (!task.deadline_at || isTerminal(task.status) || task.deleted_at) return false
  // Даты приходят в SQL-формате UTC (`YYYY-MM-DD HH:MM:SS`) — он сравнивается как строка.
  return task.deadline_at < new Date().toISOString().slice(0, 19).replace('T', ' ')
}

/** Дата строки — срок задачи; его нет, значит показывать в этом столбце нечего. */
function dateOf(task: TaskListRow): { value: string; label: string } | null {
  if (task.deadline_at) return { value: task.deadline_at, label: t('tasks.task.card.deadline_at') }
  return null
}

// Открытое меню действий: строка держит свой «⋯» видимым, пока меню раскрыто, — иначе кнопка
// исчезала бы из-под курсора, едва он ушёл на пункт списка.
const menuOpen = ref(false)
</script>

<template>
  <div
    class="task-row"
    :class="{
      'task-row--dimmed': dimmed(props.task),
      'task-row--open': props.open,
      'task-row--child': props.depth > 0,
      'task-row--last-child': props.depth > 0 && props.last,
    }"
    :style="{ '--row-depth': props.depth }"
    role="link"
    tabindex="0"
    @click="emit('open', props.task.code)"
    @keydown.enter="emit('open', props.task.code)"
  >
    <!-- Ручка есть и у подзадачи: её ряд — сёстры, и переставляют её тем же жестом. Место под
         ручку занято всегда — строка не должна вздрагивать от наведения. -->
    <DragHandle
      v-if="!props.task.deleted_at && props.reorderable !== false"
      :label="t('tasks.task.card.drag')"
      @click.stop
    />
    <span v-else class="task-row__handle-gap" />

    <!-- Состояние — глиф, а не слово: очертание узнаётся боковым зрением, и столбец значков
         пробегается сверху вниз без чтения. Название остаётся подсказкой — и `aria-label`:
         подсказка приезжает по наведению, а читалке нужно то же слово, что видит глаз. То же у
         всех остальных глифов строки. -->
    <span
      class="task-row__glyph"
      :class="`task-row__glyph--${statusColor(props.task.status)}`"
      role="img"
      :aria-label="t(`tasks.task.status.${props.task.status}`)"
    >
      <component :is="statusIcon(props.task.status)" :size="18" :stroke-width="1.6" />
      <VTooltip activator="parent" location="top">
        {{ t(`tasks.task.status.${props.task.status}`) }}
      </VTooltip>
    </span>

    <span
      class="task-row__glyph"
      :class="`task-row__glyph--${priorityColor(props.task.priority)}`"
      role="img"
      :aria-label="t(`tasks.task.priority.${props.task.priority}`)"
    >
      <component :is="priorityIcon(props.task.priority)" :size="16" :stroke-width="1.6" />
      <VTooltip activator="parent" location="top">
        {{ t(`tasks.task.priority.${props.task.priority}`) }}
      </VTooltip>
    </span>

    <!-- Название и следом за ним счёт подзадач. Всё стоит СРАЗУ за текстом, как у карточки
         группы, а не у края строки. Длинное название сжимается многоточием, счёт — никогда: в
         свёрнутой ветке он единственный её след. -->
    <span class="task-row__name">
      <span class="task-row__title" :title="props.task.title">{{ props.task.title }}</span>
      <!-- Когда ветка нарисована, счёт и стрелка — одна кнопка, та же, что у шапки группы. -->
      <CounterButton
        v-if="props.foldable"
        class="task-row__fold"
        :icon="IconSubtask"
        :count="props.childCount || undefined"
        :folded="folded"
        :label="t(folded ? 'tasks.task.card.expand_children' : 'tasks.task.card.collapse_children')"
        @toggle="store.toggleCollapsed(props.task.code)"
      />
      <!-- Ветки нет на экране (сужённая выдача) — сворачивать нечего, и счёт остаётся пометкой. -->
      <span
        v-else-if="props.childCount || props.task.has_children"
        class="task-row__mark task-row__children"
        :aria-label="t('tasks.task.detail.children')"
      >
        <IconSubtask :size="14" :stroke-width="1.6" />
        <span v-if="props.childCount">{{ props.childCount }}</span>
        <VTooltip activator="parent" location="top">{{ t('tasks.task.detail.children') }}</VTooltip>
      </span>
    </span>

    <span class="task-row__meta">
      <!-- Корзина — тоже пометка, а не шильдик: строка уже приглушена целиком, и значку
           остаётся сказать, ПОЧЕМУ она приглушена. -->
      <span
        v-if="props.task.deleted_at"
        class="task-row__mark"
        role="img"
        :aria-label="t('tasks.task.card.deleted')"
      >
        <IconTrash :size="14" :stroke-width="1.6" />
        <VTooltip activator="parent" location="top">{{ t('tasks.task.card.deleted') }}</VTooltip>
      </span>

      <span
        v-if="dateOf(props.task)"
        class="task-row__date"
        :class="{ 'task-row__date--overdue': overdue(props.task) }"
        :aria-label="`${dateOf(props.task)!.label}: ${fmtDate(dateOf(props.task)!.value)}`"
      >
        {{ fmtDateShort(dateOf(props.task)!.value) }}
        <VTooltip activator="parent" location="top">
          {{ dateOf(props.task)!.label }}: {{ fmtDate(dateOf(props.task)!.value) }}
        </VTooltip>
      </span>
    </span>

    <!-- Меню — служебный жёлоб, а не данные: клик по нему не должен открывать окно. Три точки в
         каждой строке — постоянный шум, поэтому кнопка появляется под курсором и держится, пока
         меню раскрыто. -->
    <span
      class="task-row__menu"
      :class="{ 'task-row__menu--open': menuOpen }"
      @click.stop
    >
      <VMenu v-model="menuOpen" location="bottom end" :offset="4">
        <template #activator="{ props: menu }">
          <VBtn
            v-bind="menu"
            icon
            variant="text"
            class="row-action"
            :title="t('tasks.task.card.actions')"
          >
            <IconDotsVertical :size="16" :stroke-width="1.6" />
          </VBtn>
        </template>

        <!-- Набор действий зависит от состояния: у живой — перестановка, правка, подзадача и
             удаление, у удалённой — только возврат. Править удалённую бэк не даёт (409), и
             пункт, который заведомо откажет, врал бы кнопкой. -->
        <VList density="compact">
          <template v-if="!props.task.deleted_at">
            <!-- Перестановка без мыши исчезает вместе с ручкой: на сужённом списке порядок не
                 меняют ни жестом, ни пунктом меню. -->
            <template v-if="props.reorderable !== false">
              <VListItem
                :prepend-icon="IconArrowUp"
                :disabled="!props.canUp"
                @click="emit('step', -1)"
              >
                <VListItemTitle>{{ t('tasks.task.card.move_up') }}</VListItemTitle>
              </VListItem>
              <VListItem
                :prepend-icon="IconArrowDown"
                :disabled="!props.canDown"
                @click="emit('step', 1)"
              >
                <VListItemTitle>{{ t('tasks.task.card.move_down') }}</VListItemTitle>
              </VListItem>
              <!-- Открепление — то же, что вытаскивание мышью наверх, только без места броска:
                   задача встаёт первой в своей группе, чтобы результат было видно сразу.
                   Решает наличие родителя, а не глубина строки: на странице задачи её прямые
                   подзадачи стоят верхним рядом ветки, но открепить их можно так же. -->
              <VListItem
                v-if="props.task.parent_code !== null"
                :prepend-icon="IconUnlink"
                @click="emit('detach')"
              >
                <VListItemTitle>{{ t('tasks.task.card.detach') }}</VListItemTitle>
              </VListItem>
              <VDivider class="my-1" />
            </template>
            <VListItem :prepend-icon="IconPencil" @click="emit('edit', props.task)">
              <VListItemTitle>{{ t('tasks.task.card.edit') }}</VListItemTitle>
            </VListItem>
            <VListItem :prepend-icon="IconSubtask" @click="emit('addChild', props.task)">
              <VListItemTitle>{{ t('tasks.task.card.add_child') }}</VListItemTitle>
            </VListItem>
            <VListItem
              :prepend-icon="IconTrash"
              class="task-menu-danger"
              @click="emit('remove', props.task.code)"
            >
              <VListItemTitle>{{ t('tasks.task.card.delete') }}</VListItemTitle>
            </VListItem>
          </template>
          <VListItem
            v-else
            :prepend-icon="IconArchiveOff"
            @click="emit('restore', props.task.code)"
          >
            <VListItemTitle>{{ t('tasks.task.card.restore') }}</VListItemTitle>
          </VListItem>
        </VList>
      </VMenu>
    </span>
  </div>
</template>

<style scoped>
/* Ровно 36px и одна линия содержимого. Разделитель — волосяная линия между соседними строками:
   зебра красит половину списка без всякого повода, а рамка у каждой строки превращает список в
   стопку карточек. Линия рисуется сверху, а не снизу: соседями строки бывают и контейнеры
   подзадач, и обёртки веток, и «у каждой своя верхняя граница» — единственное правило, которое
   держится при любом их порядке. */
.task-row {
  /* Сдвиг ветки задаётся здесь, а не отступом на каждом уровне: глубину строка приносит с собой
     переменной, и любой уровень вложенности считается одним умножением. */
  --row-indent: 22px;

  position: relative;
  display: flex;
  align-items: center;
  gap: 8px;
  height: 36px;
  padding: 0 8px 0 calc(6px + var(--row-depth, 0) * var(--row-indent));
  /* Строка — ссылка: клик открывает задачу, и курсор обязан это обещать. Ручка, кнопка-счётчик и
     меню ставят свой курсор поверх — у них другое действие. */
  cursor: pointer;
}

.task-row:hover,
.task-row:focus-visible { background: var(--surface-hi); outline: none; }

/* Открытая задача остаётся отмеченной и после того, как курсор ушёл: вернувшись, человек видит,
   откуда он уходил. Полоска слева, а не только фон, — иначе отметка неотличима от наведения. */
.task-row--open {
  background: var(--surface-hi);
  box-shadow: inset 2px 0 0 var(--accent);
}

/* Закрытая работа и корзина приглушены целиком, а не помечены одной меткой: такие строки не
   должны соперничать за внимание с живыми. Наведение возвращает непрозрачность — чтобы прочитать
   строку, не приходится её воскрешать. */
.task-row--dimmed { opacity: 0.55; }
.task-row--dimmed:hover { opacity: 1; }

/* Пустое место на месте ручки: у удалённой её нет, но столбцы строк обязаны совпадать. */
.task-row__handle-gap {
  width: 20px;
  flex: none;
}

/* У подзадачи ручка отступает за загиб направляющей: загиб кончается на 9px правее вертикали, а
   ручка без отступа начиналась бы раньше — и значок хвата ложился бы прямо на линию ветки.
   Сдвигается и пустое место под ручкой, иначе у удалённой подзадачи столбцы разъехались бы. */
.task-row--child .drag-handle,
.task-row--child .task-row__handle-gap {
  margin-inline-start: 8px;
}

/* Направляющая ветки: вертикаль от предыдущей строки и загиб к значку состояния. Псевдоэлемент
   не перехватывает курсор: строка кликабельна целиком, и линия не должна быть исключением. */
.task-row--child::before {
  content: '';
  position: absolute;
  top: 0;
  bottom: 50%;
  left: calc(16px + (var(--row-depth, 1) - 1) * var(--row-indent) + 9px);
  width: 9px;
  border-left: 1px solid var(--border);
  border-bottom: 1px solid var(--border);
  border-bottom-left-radius: 6px;
  pointer-events: none;
}

/* Последний ребёнок обрывает вертикаль на своём загибе, остальные продолжают её вниз — иначе
   линия кончается там, где ветка ещё продолжается. */
.task-row--child:not(.task-row--last-child)::after {
  content: '';
  position: absolute;
  top: 50%;
  bottom: 0;
  left: calc(16px + (var(--row-depth, 1) - 1) * var(--row-indent) + 9px);
  border-left: 1px solid var(--border);
  pointer-events: none;
}

/* Глиф состояния и глиф важности: единственные два места в строке, где есть цвет. */
.task-row__glyph {
  display: inline-flex;
  align-items: center;
  flex: none;
}

.task-row__glyph--accent  { color: var(--accent); }
.task-row__glyph--success { color: var(--success); }
.task-row__glyph--error   { color: var(--error); }
.task-row__glyph--warn    { color: var(--warn); }
.task-row__glyph--muted   { color: var(--text-faint); }

/* Заголовок — обычный вес и основной цвет: он и есть строка, остальное вокруг него служебное.
   Полужирный держался бы на карточке, но в списке из сотни строк жирным оказывается весь экран. */
.task-row__title {
  flex: 0 1 auto;
  min-width: 0;
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
  font-size: 13px;
  color: var(--text);
}

/* Ячейка названия забирает остаток строки, а заголовок внутри неё — только свою ширину: так
   стрелка встаёт сразу за текстом, а не у правого края. */
.task-row__name {
  display: flex;
  align-items: center;
  gap: 2px;
  flex: 1 1 auto;
  min-width: 0;
}

/* Счёт подзадач переехал из пометок к названию, но остаётся пометкой: тот же кегль и тот же
   приглушённый цвет, что у остальных справа, — иначе он читался бы продолжением заголовка.
   Отступ слева отбивает его от текста; до стрелки хватает зазора ячейки. */
.task-row__children {
  flex: none;
  margin-inline-start: 6px;
  font-size: 12px;
  color: var(--text-faint);
}

/* Вид кнопки ветки — её собственный (`CounterButton`); строка задаёт только место: отрицательный
   отступ прячет поле кнопки, и значок стоит от текста там же, где пассивный счёт выше. И
   проявляет её, пока курсор над строкой. */
.task-row__fold { margin-inline: 2px -4px; }

.task-row:hover { --counter-button-color: var(--text-muted); }

.task-row__meta {
  display: inline-flex;
  align-items: center;
  gap: 10px;
  flex: none;
  font-size: 12px;
  color: var(--text-faint);
}

.task-row__mark {
  display: inline-flex;
  align-items: center;
  gap: 3px;
}

.task-row__date { font-variant-numeric: tabular-nums; }

/* Единственная пометка, которая имеет право на цвет: срок прошёл, а работа открыта. */
.task-row__date--overdue { color: var(--warn); }

.task-row__menu {
  display: inline-flex;
  flex: none;
  width: 28px;
  opacity: 0;
  transition: opacity 0.12s ease;
}

.task-row:hover .task-row__menu,
.task-row:focus-within .task-row__menu,
.task-row__menu--open { opacity: 1; }

.task-row__menu :deep(.v-btn) {
  width: 28px;
  min-width: 28px;
  height: 28px;
}

.task-menu-danger :deep(.v-list-item-title) { color: var(--error); }
.task-menu-danger :deep(.v-list-item__prepend) { color: var(--error); }
</style>
