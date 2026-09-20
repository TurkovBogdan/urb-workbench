<script setup lang="ts">
// Строки одной карточки группы и перетаскивание между ними.
//
// Отдельным компонентом, а не куском списка, ровно по одной причине: sortable заводится НА
// КОНТЕЙНЕР, а контейнеров столько же, сколько групп. Композабл живёт в setup, и на переменное
// число секций его иначе не позвать.
//
// ПЕРЕТАСКИВАЕТСЯ ВЕТКА, а не строка: задача уезжает вместе со своими подзадачами, поэтому
// соседями в контейнере стоят обёртки веток, а строки лежат внутри них.
//
// Жест собран на Pointer Events (`forceFallback: true`), а не на нативном HTML5 DnD. Нативный
// оправдан только для файлов из ОС и переноса между окнами: от пальца он не шлёт событий ни в
// одном мобильном браузере, не даёт управлять превью и запрещает прокрутку во время жеста.
//
// Взять можно за РУЧКУ, а не за строку целиком: иначе жест отнимает у строки выделение текста, а
// на тач-устройстве — прокрутку списка.
//
// Мышь — не единственный путь: те же две перестановки есть пунктами меню строки («Выше», «Ниже»).
// Это не удобство, а требование — WCAG 2.2 SC 2.5.7 просит альтернативу перетаскиванию одним
// нажатием указателя, а меню, открываемое с клавиатуры, закрывает заодно и SC 2.1.1.
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useDraggable } from 'vue-draggable-plus'
import {
  IconArchiveOff,
  IconArrowDown,
  IconArrowUp,
  IconDotsVertical,
  IconListCheck,
  IconPencil,
  IconSubtask,
  IconTrash,
} from '@tabler/icons-vue'

import DragHandle from '@/components/DragHandle.vue'
import { fmtDate, fmtDateShort } from '@/shared/utils/date'

import {
  isTerminal,
  priorityColor,
  priorityIcon,
  statusColor,
  statusIcon,
  TASK_TYPE_DEFAULT,
} from '../labels'
import type { TaskSection } from '../stores/tasks.store'
import type { TaskListRow } from '../api'

/** Ход анимации перестановки соседей — штатный FLIP библиотеки. */
const ANIMATION_MS = 150

const props = defineProps<{
  section: TaskSection
  /** Код задачи, на которую уходили со списка: её строка остаётся отмеченной. */
  openCode?: string | null
  /** Сколько подзадач у каждой задачи — считает список, здесь только показ. */
  childCounts: Map<string, number>
}>()

const emit = defineEmits<{
  open: [code: string]
  edit: [task: TaskListRow]
  addChild: [task: TaskListRow]
  remove: [code: string]
  restore: [code: string]
  /** Ветка переехала: под какую строку легла и в какой группе (`undefined` — группа не менялась). */
  move: [payload: { code: string; after: string | null; group?: string | null }]
}>()

const { t } = useI18n()

/** Ключ группы в разметке: пустая строка — «Без группы», её код в `dataset` иначе неотличим от отсутствия. */
const groupKey = computed(() => props.section.group?.code ?? '')

const container = ref<HTMLElement | null>(null)

// Список, который двигает сама библиотека. Рисуем мы не его, а `section.branches` из стора —
// он остаётся источником правды, а этот массив нужен sortable, чтобы вести своё состояние.
const codes = ref<string[]>([])

watch(
  () => props.section.branches,
  (branches) => { codes.value = branches.map((branch) => branch.root.code) },
  { immediate: true },
)

useDraggable(container, codes, {
  // Общее имя sortable-группы у всех карточек — этим и работает перенос задачи в чужую группу.
  group: { name: 'tasks' },
  handle: '.drag-handle',
  draggable: '.task-branch',
  animation: ANIMATION_MS,
  // Pointer Events вместо нативного DnD (см. шапку файла).
  forceFallback: true,
  fallbackOnBody: true,
  ghostClass: 'task-branch--ghost',
  chosenClass: 'task-branch--chosen',
  dragClass: 'task-branch--drag',
  fallbackClass: 'task-branch--preview',
  // Порог захвата: короткое движение по строке остаётся кликом, а не начинает перенос.
  fallbackTolerance: 4,
  // Автопрокрутка нужна, когда карточка не помещается в экран целиком.
  scroll: true,
  scrollSensitivity: 80,
  onEnd: (event) => {
    const item = event.item as HTMLElement
    const code = item.dataset.code
    if (!code) return
    const to = event.to as HTMLElement
    // Жест кончился там же, где начался: ветку подняли и положили обратно. Запрос на это слать
    // нельзя — позиция названа соседом, и «после соседа сверху» для нетронутого ряда означает
    // перестановку, которой никто не просил.
    if (to === event.from && event.oldIndex === event.newIndex) return
    // Соседа берём из РАЗМЕТКИ, уже переставленной библиотекой: это и есть то, что человек видит.
    const previous = item.previousElementSibling as HTMLElement | null
    emit('move', {
      code,
      after: previous?.dataset.code ?? null,
      group: to === event.from ? undefined : (to.dataset.group || null),
    })
  },
})

// ── Тот же перенос без мыши ───────────────────────────────────────────────────
// «Выше» — встать после того, кто стоял через одного: иначе перестановка с соседом ничего не
// меняет. «Ниже» — после ближайшего соседа снизу.
function neighbourFor(code: string, direction: -1 | 1): string | null | undefined {
  const order = props.section.branches.map((branch) => branch.root.code)
  const at = order.indexOf(code)
  if (at === -1) return undefined
  const target = at + direction
  if (target < 0 || target >= order.length) return undefined
  return direction === -1 ? (target > 0 ? order[target - 1] : null) : order[target]
}

function canMove(code: string, direction: -1 | 1): boolean {
  return neighbourFor(code, direction) !== undefined
}

function moveBy(code: string, direction: -1 | 1): void {
  const after = neighbourFor(code, direction)
  if (after === undefined) return
  emit('move', { code, after })
}

// ── Показ строки ──────────────────────────────────────────────────────────────

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

function childCount(task: TaskListRow): number {
  return props.childCounts.get(task.code) ?? 0
}

// Открытое меню действий: строка держит свой «⋯» видимым, пока меню раскрыто, — иначе кнопка
// исчезала бы из-под курсора, едва он ушёл на пункт списка.
const menuFor = ref<string | null>(null)

function toggleMenu(code: string, open: boolean) {
  menuFor.value = open ? code : null
}
</script>

<template>
  <div
    ref="container"
    class="task-rows"
    :class="{ 'task-rows--empty': !section.branches.length }"
    :data-group="groupKey"
  >
    <!-- Подпись пустой секции лежит ВНУТРИ контейнера sortable, а не рядом с ним: контейнер без
         детей схлопнулся бы в ноль, и попасть в него курсором с веткой было бы не во что.
         Перетаскиваются только `.task-branch`, поэтому подпись остаётся на месте и в жесте не
         участвует — она лишь держит высоту и объясняет, зачем эта карточка тут стоит. -->
    <p v-if="!section.branches.length" class="task-rows__hint">
      {{ t('tasks.task.list.group_empty') }}
    </p>

    <div
      v-for="branch in section.branches"
      :key="branch.root.code"
      class="task-branch"
      :data-code="branch.root.code"
    >
      <div
        v-for="{ task, depth, last } in branch.rows"
        :key="task.code"
        class="task-row"
        :class="{
          'task-row--dimmed': dimmed(task),
          'task-row--open': task.code === props.openCode,
          'task-row--child': depth > 0,
          'task-row--last-child': depth > 0 && last,
        }"
        :style="{ '--row-depth': depth }"
        role="link"
        tabindex="0"
        @click="emit('open', task.code)"
        @keydown.enter="emit('open', task.code)"
      >
        <!-- Ручка только у верхнего уровня: подзадача едет со своей веткой, и своей ручки ей не
             положено. Место под ручку занято всегда — строка не должна вздрагивать от наведения. -->
        <DragHandle
          v-if="depth === 0 && !task.deleted_at"
          :label="t('tasks.task.card.drag')"
          @click.stop
        />
        <span v-else class="task-row__handle-gap" />

        <!-- Состояние — глиф, а не слово: очертание узнаётся боковым зрением, и столбец
             значков пробегается сверху вниз без чтения. Название остаётся подсказкой — и
             `aria-label`: подсказка приезжает по наведению, а читалке нужно то же слово, что
             видит глаз. То же у всех остальных глифов строки. -->
        <span
          class="task-row__glyph"
          :class="`task-row__glyph--${statusColor(task.status)}`"
          role="img"
          :aria-label="t(`tasks.task.status.${task.status}`)"
        >
          <component :is="statusIcon(task.status)" :size="18" :stroke-width="1.6" />
          <VTooltip activator="parent" location="top">
            {{ t(`tasks.task.status.${task.status}`) }}
          </VTooltip>
        </span>

        <span
          class="task-row__glyph"
          :class="`task-row__glyph--${priorityColor(task.priority)}`"
          role="img"
          :aria-label="t(`tasks.task.priority.${task.priority}`)"
        >
          <component :is="priorityIcon(task.priority)" :size="16" :stroke-width="1.6" />
          <VTooltip activator="parent" location="top">
            {{ t(`tasks.task.priority.${task.priority}`) }}
          </VTooltip>
        </span>

        <span class="task-row__title" :title="task.title">{{ task.title }}</span>

        <span class="task-row__meta">
          <!-- Простая задача тип не показывает: это умолчание, и значок на каждой второй строке
               перестал бы что-либо значить. Пометка говорит: внутри есть план. -->
          <span
            v-if="task.type !== TASK_TYPE_DEFAULT"
            class="task-row__mark"
            role="img"
            :aria-label="t(`tasks.task.type.${task.type}`)"
          >
            <IconListCheck :size="14" :stroke-width="1.6" />
            <VTooltip activator="parent" location="top">
              {{ t(`tasks.task.type.${task.type}`) }}
            </VTooltip>
          </span>

          <span
            v-if="childCount(task) || task.has_children"
            class="task-row__mark"
            :aria-label="t('tasks.task.detail.children')"
          >
            <IconSubtask :size="14" :stroke-width="1.6" />
            <span v-if="childCount(task)">{{ childCount(task) }}</span>
            <VTooltip activator="parent" location="top">{{ t('tasks.task.detail.children') }}</VTooltip>
          </span>

          <!-- Корзина — тоже пометка, а не шильдик: строка уже приглушена целиком, и значку
               остаётся сказать, ПОЧЕМУ она приглушена. -->
          <span
            v-if="task.deleted_at"
            class="task-row__mark"
            role="img"
            :aria-label="t('tasks.task.card.deleted')"
          >
            <IconTrash :size="14" :stroke-width="1.6" />
            <VTooltip activator="parent" location="top">{{ t('tasks.task.card.deleted') }}</VTooltip>
          </span>

          <span
            v-if="dateOf(task)"
            class="task-row__date"
            :class="{ 'task-row__date--overdue': overdue(task) }"
            :aria-label="`${dateOf(task)!.label}: ${fmtDate(dateOf(task)!.value)}`"
          >
            {{ fmtDateShort(dateOf(task)!.value) }}
            <VTooltip activator="parent" location="top">
              {{ dateOf(task)!.label }}: {{ fmtDate(dateOf(task)!.value) }}
            </VTooltip>
          </span>
        </span>

        <!-- Меню — служебный жёлоб, а не данные: клик по нему не должен открывать окно. Три
             точки в каждой строке — постоянный шум, поэтому кнопка появляется под курсором и
             держится, пока меню раскрыто. -->
        <span
          class="task-row__menu"
          :class="{ 'task-row__menu--open': menuFor === task.code }"
          @click.stop
        >
          <VMenu
            :model-value="menuFor === task.code"
            location="bottom end"
            :offset="4"
            @update:model-value="toggleMenu(task.code, $event)"
          >
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
              <template v-if="!task.deleted_at">
                <template v-if="depth === 0">
                  <VListItem
                    :prepend-icon="IconArrowUp"
                    :disabled="!canMove(task.code, -1)"
                    @click="moveBy(task.code, -1)"
                  >
                    <VListItemTitle>{{ t('tasks.task.card.move_up') }}</VListItemTitle>
                  </VListItem>
                  <VListItem
                    :prepend-icon="IconArrowDown"
                    :disabled="!canMove(task.code, 1)"
                    @click="moveBy(task.code, 1)"
                  >
                    <VListItemTitle>{{ t('tasks.task.card.move_down') }}</VListItemTitle>
                  </VListItem>
                  <VDivider class="my-1" />
                </template>
                <VListItem :prepend-icon="IconPencil" @click="emit('edit', task)">
                  <VListItemTitle>{{ t('tasks.task.card.edit') }}</VListItemTitle>
                </VListItem>
                <VListItem :prepend-icon="IconSubtask" @click="emit('addChild', task)">
                  <VListItemTitle>{{ t('tasks.task.card.add_child') }}</VListItemTitle>
                </VListItem>
                <VListItem
                  :prepend-icon="IconTrash"
                  class="task-menu-danger"
                  @click="emit('remove', task.code)"
                >
                  <VListItemTitle>{{ t('tasks.task.card.delete') }}</VListItemTitle>
                </VListItem>
              </template>
              <VListItem v-else :prepend-icon="IconArchiveOff" @click="emit('restore', task.code)">
                <VListItemTitle>{{ t('tasks.task.card.restore') }}</VListItemTitle>
              </VListItem>
            </VList>
          </VMenu>
        </span>
      </div>
    </div>
  </div>
</template>

<style scoped>
/* ── Пустая секция ─────────────────────────────────────────────────────────────
   Высота задана здесь, а не подписью внутри: подпись уедет, как только в группу что-нибудь
   положат, а цель для переноса обязана быть достаточно крупной, чтобы в неё попасть рукой. */
.task-rows--empty {
  display: flex;
  align-items: center;
  min-height: 44px;
}

.task-rows__hint {
  margin: 0;
  padding: 0 12px;
  font-size: 12px;
  line-height: 16px;
  color: var(--text-faint);
}

/* ── Ветка ─────────────────────────────────────────────────────────────────────
   Обёртка существует ради перетаскивания: своей внешности у неё нет, но именно она ездит —
   вместе со всеми строками внутри. */
.task-branch + .task-branch { border-top: 1px solid var(--border-soft); }

/* Место, откуда ветку взяли: тень исходного положения. Цвет из токенов темы — жёсткий цвет
   пережил бы переключение на светлую схему как чужой. */
.task-branch--ghost {
  opacity: 0.4;
  background: var(--accent-soft);
}

.task-branch--ghost .task-row { background: transparent; }

/* Превью под курсором: приподнято тенью и слегка уменьшено — «взято в руку». В движении
   меняются только `transform` и `opacity`: свойства, которые не заставляют браузер
   пересчитывать раскладку на каждый кадр. */
.task-branch--preview {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  box-shadow: 0 12px 32px rgba(0, 0, 0, 0.28);
  opacity: 0.95;
  transform: scale(0.99);
  cursor: grabbing;
}

/* Пока ветку держат, её строки не отвечают на наведение: подсветка под курсором в этот момент
   означала бы «сюда положить», а положить в самого себя нельзя. */
.task-branch--chosen .task-row:hover { background: transparent; }

/* ── Строка ────────────────────────────────────────────────────────────────────
   Ровно 36px и одна линия содержимого. Разделитель — волосяная линия между соседними строками:
   зебра красит половину списка без всякого повода, а рамка у каждой строки превращает список в
   стопку карточек. */
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
}

.task-row + .task-row { border-top: 1px solid var(--border-soft); }

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

/* Пустое место на месте ручки: подзадача её не имеет, но столбцы строк обязаны совпадать. */
.task-row__handle-gap {
  width: 20px;
  flex: none;
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
  flex: 1 1 auto;
  min-width: 0;
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
  font-size: 13px;
  color: var(--text);
}

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
