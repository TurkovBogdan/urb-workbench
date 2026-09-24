<script setup lang="ts">
// Ряд корней одной карточки группы и перетаскивание между карточками.
//
// Отдельным компонентом, а не куском списка, ровно по одной причине: sortable заводится НА
// КОНТЕЙНЕР, а контейнеров столько же, сколько карточек. Композабл живёт в setup, и на переменное
// число секций его иначе не позвать. По той же причине дети одного родителя живут в своём
// компоненте (`TaskSubtree`): у них свой контейнер и свой ряд соседей.
//
// ПЕРЕТАСКИВАЕТСЯ ВЕТКА ЦЕЛИКОМ: корень уезжает вместе со своими подзадачами, потому что они
// лежат внутри его обёртки.
//
// Жест собран на Pointer Events (`forceFallback: true`), а не на нативном HTML5 DnD. Нативный
// оправдан только для файлов из ОС и переноса между окнами: от пальца он не шлёт событий ни в
// одном мобильном браузере, не даёт управлять превью и запрещает прокрутку во время жеста.
//
// Взять можно за РУЧКУ, а не за строку целиком: иначе жест отнимает у строки выделение текста, а
// на тач-устройстве — прокрутку списка.
//
// Мышь — не единственный путь: те же перестановки есть пунктами меню строки. Это не удобство, а
// требование — WCAG 2.2 SC 2.5.7 просит альтернативу перетаскиванию одним нажатием указателя, а
// меню, открываемое с клавиатуры, закрывает заодно и SC 2.1.1.
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useDraggable } from 'vue-draggable-plus'

import TaskRow from './TaskRow.vue'
import TaskSubtree from './TaskSubtree.vue'
import { anchorAfterDrop } from '../drag'
import { useTasksStore, type TaskSection } from '../stores/tasks.store'
import type { TaskListRow } from '../api'

/** Ход анимации перестановки соседей — штатный FLIP библиотеки. */
const ANIMATION_MS = 150

const props = defineProps<{
  section: TaskSection
  /** Код задачи, на которую уходили со списка: её строка остаётся отмеченной. */
  openCode?: string | null
  /** Сколько подзадач у каждой задачи — считает список, здесь только показ. */
  childCounts: Map<string, number>
  /**
   * Порядок в этой выдаче можно менять.
   *
   * Выключается на сужённом списке: там показана ВЫБОРКА, а не раскладка — ветки не рисуются,
   * соседи по группе на экране не все, и перестановка относительно видимого соседа означала бы
   * не то, что человек видит. Ручка при этом прячется: жест, который ничего не делает, хуже
   * отсутствующего.
   */
  reorderable?: boolean
}>()

const emit = defineEmits<{
  open: [code: string]
  edit: [task: TaskListRow]
  addChild: [task: TaskListRow]
  remove: [code: string]
  restore: [code: string]
  /**
   * Строка переехала: под какую легла, в какой она группе и чья она теперь.
   *
   * `group` отсутствует — группу не трогаем; `parent` отсутствует — родителя не трогаем, `null` —
   * открепить. Те же три ключа уезжают в один запрос: одно движение мышью не должно показывать
   * промежуточных состояний.
   */
  move: [payload: {
    code: string
    after: string | null
    group?: string | null
    parent?: string | null
  }]
}>()

const { t } = useI18n()
// Стор нужен ради одного — свёрнута ли ветка под строкой: состояние живёт там, рядом со
// свёрнутостью карточек групп, и держится до смены пространства.
const store = useTasksStore()

/** Ключ группы в разметке: пустая строка — «Без группы», её код в `dataset` иначе неотличим от отсутствия. */
const groupKey = computed(() => props.section.group?.code ?? '')

const container = ref<HTMLElement | null>(null)

// Список, который двигает сама библиотека. Рисуем мы не его, а `section.branches` из стора —
// он остаётся источником правды, а этот массив нужен sortable, чтобы вести своё состояние.
const codes = ref<string[]>([])

watch(
  () => props.section.branches,
  (branches) => { codes.value = branches.map((node) => node.task.code) },
  { immediate: true },
)

const sortable = useDraggable(container, codes, {
  // Общее имя sortable-группы у всех карточек — этим и работает перенос задачи в чужую группу.
  // `put` открыт: сюда падают и корни из соседних карточек, и подзадачи, вытащенные из веток, —
  // второе и есть открепление.
  group: { name: 'tasks', pull: true, put: true },
  handle: '.drag-handle',
  draggable: '.task-drag',
  // Ручка принадлежит ТОМУ контейнеру, в котором лежит. Без этого жест начинают оба sortable
  // разом — внешний берёт ветку, внутренний подзадачу, — и не двигается ничто: два захвата
  // спорят за один указатель. Селектором это не выразить (`.task-subtree` отфильтровал бы и сам
  // вложенный контейнер вместе с его строками), поэтому решает функция: чей это контейнер.
  filter: (event: Event) =>
    (event.target as HTMLElement | null)?.closest('.task-subtree, .task-rows') !== container.value,
  animation: ANIMATION_MS,
  // Pointer Events вместо нативного DnD (см. шапку файла).
  forceFallback: true,
  fallbackOnBody: true,
  ghostClass: 'task-drag--ghost',
  chosenClass: 'task-drag--chosen',
  dragClass: 'task-drag--drag',
  fallbackClass: 'task-drag--preview',
  // Порог захвата: короткое движение по строке остаётся кликом, а не начинает перенос.
  fallbackTolerance: 4,
  // Автопрокрутка нужна, когда карточка не помещается в экран целиком.
  scroll: true,
  scrollSensitivity: 80,
  onStart: () => { store.dragging = true },
  onEnd: (event) => {
    store.dragging = false
    const item = event.item as HTMLElement
    const code = item.dataset.code
    if (!code) return
    const to = event.to as HTMLElement
    const from = event.from as HTMLElement
    const sameContainer = to === from
    // Жест кончился там же, где начался: ветку подняли и положили обратно. Запрос на это слать
    // нельзя — позиция названа соседом, и «после соседа сверху» для нетронутого ряда означает
    // перестановку, которой никто не просил.
    if (sameContainer && event.oldIndex === event.newIndex) return
    // Брошена на шапку СВОЕЙ же карточки: в конец своего ряда её так не отправить — шапка значит
    // «в эту группу», а она уже в ней. Жест без смысла, и запроса он не стоит.
    if (to.dataset.drop === 'end' && to.dataset.group === groupKey.value) return
    // Сюда приходит только перенос КОРНЯ — своего или из соседней карточки: `onEnd` достаётся
    // тому sortable, с которого жест начался, а вытащенную из ветки подзадачу разбирает её
    // собственный контейнер (`TaskSubtree`), он же и знает, что это открепление.
    emit('move', {
      code,
      after: anchorAfterDrop(to, code, event.newIndex),
      ...(sameContainer ? {} : { group: to.dataset.group || null }),
    })
  },
})

watch(
  () => props.reorderable !== false,
  (on) => { if (on) sortable.resume(); else sortable.pause() },
  { immediate: true },
)

// ── Тот же перенос без мыши ───────────────────────────────────────────────────
// «Выше» — встать после того, кто стоял через одного: иначе перестановка с соседом ничего не
// меняет. «Ниже» — после ближайшего соседа снизу.

function neighbourFor(code: string, direction: -1 | 1): string | null | undefined {
  const order = props.section.branches.map((node) => node.task.code)
  const at = order.indexOf(code)
  if (at === -1) return undefined
  const target = at + direction
  if (target < 0 || target >= order.length) return undefined
  return direction === -1 ? (target > 0 ? order[target - 1] : null) : order[target]
}

function canStep(code: string, direction: -1 | 1): boolean {
  return neighbourFor(code, direction) !== undefined
}

function step(code: string, direction: -1 | 1): void {
  const after = neighbourFor(code, direction)
  if (after === undefined) return
  emit('move', { code, after })
}

/**
 * Из ветки пришло перемещение. Перестановка среди сестёр уезжает как есть; открепление — тоже,
 * но если группу не назвали (так бывает у пункта меню: места броска у него нет), карточка
 * подставляет свою — открепиться «в никуда» задача не может, она обязана где-то встать.
 */
function fromSubtree(payload: {
  code: string
  after: string | null
  parent?: string | null
  group?: string | null
}): void {
  if (payload.parent === null && !('group' in payload)) {
    emit('move', { ...payload, group: groupKey.value || null })
    return
  }
  emit('move', payload)
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
         Перетаскиваются только `.task-drag`, поэтому подпись остаётся на месте и в жесте не
         участвует — она лишь держит высоту и объясняет, зачем эта карточка тут стоит. -->
    <p v-if="!section.branches.length" class="task-rows__hint">
      {{ t('tasks.task.list.group_empty') }}
    </p>

    <div
      v-for="node in section.branches"
      :key="node.task.code"
      class="task-drag task-branch"
      :data-code="node.task.code"
    >
      <TaskRow
        :task="node.task"
        :depth="0"
        :last="true"
        :child-count="props.childCounts.get(node.task.code) ?? 0"
        :open="node.task.code === props.openCode"
        :reorderable="props.reorderable"
        :can-up="canStep(node.task.code, -1)"
        :can-down="canStep(node.task.code, 1)"
        :foldable="node.children.length > 0"
        @open="emit('open', $event)"
        @edit="emit('edit', $event)"
        @add-child="emit('addChild', $event)"
        @remove="emit('remove', $event)"
        @restore="emit('restore', $event)"
        @step="step(node.task.code, $event)"
      />

      <TaskSubtree
        v-if="node.children.length && !store.isCollapsed(node.task.code)"
        :nodes="node.children"
        :parent-code="node.task.code"
        :child-counts="props.childCounts"
        :open-code="props.openCode"
        :reorderable="props.reorderable"
        @open="emit('open', $event)"
        @edit="emit('edit', $event)"
        @add-child="emit('addChild', $event)"
        @remove="emit('remove', $event)"
        @restore="emit('restore', $event)"
        @move="fromSubtree"
      />
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

/* Состояния жеста общие для веток и подзадач: и те и другие ездят обёрткой `.task-drag`, и
   выглядеть одинаковый жест обязан одинаково. */
:deep(.task-drag--ghost) {
  opacity: 0.4;
  background: var(--accent-soft);
}

:deep(.task-drag--ghost) .task-row { background: transparent; }

/* Превью под курсором: приподнято тенью и слегка уменьшено — «взято в руку». В движении
   меняются только `transform` и `opacity`: свойства, которые не заставляют браузер
   пересчитывать раскладку на каждый кадр. */
:deep(.task-drag--preview) {
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
:deep(.task-drag--chosen) .task-row:hover { background: transparent; }
</style>
