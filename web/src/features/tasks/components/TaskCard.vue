<script setup lang="ts">
// Подзадача в карточке родителя: название, состояние и даты — ровно то, по чему решают, стоит
// ли в неё заходить.
//
// Карточка, а не строка таблицы: подзадач у задачи единицы, колонок им не из чего набрать, а
// таблица из трёх строк внутри модального окна читалась бы как обломок списка. Сам список
// верхнего уровня — наоборот, таблица (`TaskListTable`): там строк сотни и сравнивать их между
// собой можно только по колонкам.
//
// Действий карточка не несёт: из окна их набор один и тот же (открыть), а править и удалять
// подзадачу идут в её собственное окно.
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { IconAlarm, IconSubtask } from '@tabler/icons-vue'

import StatusBadge from '@/components/StatusBadge.vue'
import { fmtDate } from '@/shared/utils/date'

import type { TaskListRow } from '../api'
import {
  isTerminal,
  priorityColor,
  statusColor,
  TASK_PRIORITY_DEFAULT,
  TASK_TYPE_DEFAULT,
} from '../labels'

const props = defineProps<{ task: TaskListRow }>()
const emit = defineEmits<{ open: [] }>()

const { t } = useI18n()

// Обычный приоритет не показывается: он у большинства задач, и шильдик «обычный» на каждой
// строке говорил бы ровно ничего, зато отнимал бы внимание у тех, что важны.
const priorityShown = computed(() => props.task.priority !== TASK_PRIORITY_DEFAULT)

// Простая задача тип не показывает: это умолчание. Шильдик появляется там, где у задачи есть
// план — по нему и видно, что внутри не одна строка названия.
const typeShown = computed(() => props.task.type !== TASK_TYPE_DEFAULT)

const dimmed = computed(() => isTerminal(props.task.status) || props.task.deleted_at !== null)
</script>

<template>
  <article
    class="task-card"
    :class="{ 'task-card--dimmed': dimmed, 'task-card--deleted': task.deleted_at }"
    role="link"
    tabindex="0"
    @click="emit('open')"
    @keydown.enter="emit('open')"
  >
    <header class="task-card__header">
      <StatusBadge :color="statusColor(task.status)">
        {{ t(`tasks.task.status.${task.status}`) }}
      </StatusBadge>

      <h4 class="task-card__title">{{ task.title }}</h4>

      <VChip v-if="priorityShown" size="x-small" variant="tonal" :color="priorityColor(task.priority)">
        {{ t(`tasks.task.priority.${task.priority}`) }}
      </VChip>

      <VChip v-if="typeShown" size="x-small" variant="tonal">
        {{ t(`tasks.task.type.${task.type}`) }}
      </VChip>

      <!-- Отметка корзины рядом с именем, а не в подвале: она меняет смысл всей карточки, и
           узнать о ней надо раньше, чем дойдёшь до сроков. -->
      <VChip v-if="task.deleted_at" size="x-small" variant="tonal" color="error">
        {{ t('tasks.task.card.deleted') }}
      </VChip>
    </header>

    <p v-if="task.description" class="task-card__desc">{{ task.description }}</p>

    <footer class="task-card__meta">
      <span v-if="task.deadline_at" class="task-card__meta-item task-card__meta-item--due">
        <IconAlarm :size="14" :stroke-width="1.6" />
        {{ fmtDate(task.deadline_at) }}
        <VTooltip activator="parent" location="top">{{ t('tasks.task.card.deadline_at') }}</VTooltip>
      </span>

      <!-- Признак ветки, а не счётчик: сколько именно внутри — вопрос страницы задачи, а здесь
           важно лишь то, что строка не конечная. -->
      <span v-if="task.has_children" class="task-card__meta-item">
        <IconSubtask :size="14" :stroke-width="1.6" />
        {{ t('tasks.task.card.has_children') }}
      </span>

    </footer>
  </article>
</template>

<style scoped>
.task-card {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 12px 14px;
  border: 1px solid var(--border);
  border-radius: 10px;
  background: var(--surface);
  cursor: pointer;
  transition: border-color 0.14s ease, background 0.14s ease;
}

.task-card:hover,
.task-card:focus-visible {
  border-color: var(--accent);
  outline: none;
}

/* Закрытая работа и корзина приглушены целиком, а не помечены одной меткой: такие карточки не
   должны соперничать за внимание с живыми в том же ряду. Наведение возвращает непрозрачность —
   чтобы прочитать карточку, не приходится её воскрешать. */
.task-card--dimmed { opacity: 0.6; }
.task-card--dimmed:hover { opacity: 1; }
.task-card--deleted { border-style: dashed; }

.task-card__header {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

/* Имя занимает ровно одну строку и обрезается многоточием: строки списка одинаковой высоты
   читаются сверху вниз, а разноэтажные приходится разглядывать. */
.task-card__title {
  flex: 1;
  min-width: 0;
  margin: 0;
  font-size: 14px;
  font-weight: 600;
  line-height: 1.35;
  color: var(--text);
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
}

.task-card__desc {
  margin: 0;
  font-size: 12px;
  line-height: 1.5;
  color: var(--text-muted);
  overflow: hidden;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  line-clamp: 2;
  -webkit-box-orient: vertical;
}

.task-card__meta {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 12px;
  font-size: 11px;
  color: var(--text-faint);
}

.task-card__meta:empty { display: none; }

/* Дата не переносится: разорванная посередине она перестаёт читаться как дата. */
.task-card__meta-item {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  white-space: nowrap;
}

.task-card__meta-item--due { color: var(--warn); }

</style>
