<script setup lang="ts">
// Контейнер детей ОДНОГО родителя и перетаскивание внутри него.
//
// Отдельным компонентом и рекурсивно — по той же причине, по которой ряды корней живут в
// `TaskRows`: sortable заводится НА КОНТЕЙНЕР, а контейнеров столько же, сколько родителей с
// детьми. Пока ветка рисовалась плоским списком строк, такого контейнера не было вовсе, и
// переставить подзадачу среди сестёр было нечем.
//
// ПРАВИЛА ЖЕСТА ВЫРАЖЕНЫ ГРУППОЙ SORTABLE, а не проверками в обработчике. `put: false` — внутрь
// ветки со стороны не бросишь: ни корень (он не должен становиться подзадачей перетаскиванием),
// ни подзадачу из чужой ветки (смена родителя — это перенос ветки, у него свой разговор).
// Перестановка среди СВОИХ сестёр `put` не спрашивает и работает.
//
// `pull: true` при этом оставлен: вытащить подзадачу наверх, в контейнер карточки группы, можно —
// это и есть открепление. Принимающая сторона (`TaskRows`) решает, брать ли её.
import { ref, watch } from 'vue'
import { useDraggable } from 'vue-draggable-plus'

import TaskRow from './TaskRow.vue'
import { anchorAfterDrop } from '../drag'
import { useTasksStore, type TaskNode } from '../stores/tasks.store'
import type { TaskListRow } from '../api'

/** Ход анимации перестановки соседей — штатный FLIP библиотеки, тот же, что у рядов корней. */
const ANIMATION_MS = 150

const props = defineProps<{
  /** Дети одного родителя — узлами: у каждого свои дети, глубина и место в ряду. */
  nodes: TaskNode[]
  /** Код родителя: контейнер помечен им, чтобы обработчик знал, откуда уехала строка. */
  parentCode: string
  childCounts: Map<string, number>
  openCode?: string | null
  reorderable?: boolean
}>()

const emit = defineEmits<{
  open: [code: string]
  edit: [task: TaskListRow]
  addChild: [task: TaskListRow]
  remove: [code: string]
  restore: [code: string]
  /**
   * Строка переехала: место среди сестёр, а при откреплении — ещё и `parent: null` с группой
   * той карточки, в которую её бросили. Группу знает только жест; пункт меню её не называет, и
   * подставляет её карточка.
   */
  move: [payload: {
    code: string
    after: string | null
    parent?: string | null
    group?: string | null
  }]
}>()

// Свёрнута ли ветка под строкой — см. тот же стор в `TaskRows`.
const store = useTasksStore()

const container = ref<HTMLElement | null>(null)

// Список, который двигает сама библиотека. Рисуем мы не его, а `nodes` из стора — он остаётся
// источником правды, а этот массив нужен sortable, чтобы вести своё состояние.
const codes = ref<string[]>([])

watch(
  () => props.nodes,
  (nodes) => { codes.value = nodes.map((node) => node.task.code) },
  { immediate: true },
)

const sortable = useDraggable(container, codes, {
  group: { name: 'tasks', pull: true, put: false },
  handle: '.drag-handle',
  draggable: '.task-drag',
  // Ручка из ВЛОЖЕННОГО контейнера принадлежит ему, а не нам (см. тот же фильтр в `TaskRows`).
  filter: (event: Event) =>
    (event.target as HTMLElement | null)?.closest('.task-subtree, .task-rows') !== container.value,
  animation: ANIMATION_MS,
  // Pointer Events вместо нативного DnD — по тем же причинам, что и у рядов корней.
  forceFallback: true,
  fallbackOnBody: true,
  ghostClass: 'task-drag--ghost',
  chosenClass: 'task-drag--chosen',
  dragClass: 'task-drag--drag',
  fallbackClass: 'task-drag--preview',
  fallbackTolerance: 4,
  scroll: true,
  scrollSensitivity: 80,
  onStart: () => { store.dragging = true },
  onEnd: (event) => {
    store.dragging = false
    const item = event.item as HTMLElement
    const code = item.dataset.code
    if (!code) return
    const to = event.to as HTMLElement
    const after = anchorAfterDrop(to, code, event.newIndex)

    // Жест разбирает ИСТОЧНИК, а не приёмник: `onEnd` библиотека шлёт тому sortable, с которого
    // перетаскивание началось, — принимающий получает только `onAdd` и про исходную ветку не
    // знает. Отсюда и решение здесь: подзадача уехала в контейнер корней (у него в разметке
    // помечена группа) — значит её вытащили из ветки, и это открепление.
    if (to !== event.from) {
      if (to.dataset.group === undefined) return
      emit('move', { code, after, parent: null, group: to.dataset.group || null })
      return
    }

    if (event.oldIndex === event.newIndex) return
    emit('move', { code, after })
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
  const order = props.nodes.map((node) => node.task.code)
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
 * Открепление пунктом меню. Места броска у пункта нет, и задача встаёт НАВЕРХ ряда своей группы
 * (`after: null`).
 *
 * Наверх, а не в конец, хотя свежая задача кладётся вниз: откреплённая не свежая, её только что
 * достали из ветки руками — и человек должен увидеть, что получилось, а не искать строку в хвосте
 * карточки. У жеста этого вопроса нет вовсе: там место названо броском.
 */
function detach(code: string): void {
  emit('move', { code, after: null, parent: null })
}
</script>

<template>
  <div ref="container" class="task-subtree" :data-parent="props.parentCode">
    <div
      v-for="node in props.nodes"
      :key="node.task.code"
      class="task-drag task-subtree__item"
      :data-code="node.task.code"
    >
      <TaskRow
        :task="node.task"
        :depth="node.depth"
        :last="node.last"
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
        @detach="detach(node.task.code)"
      />

      <!-- Рекурсия: у ребёнка свои дети, и у них свой контейнер со своим sortable. -->
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
        @move="emit('move', $event)"
      />
    </div>
  </div>
</template>

<style scoped>
/* Своей внешности у контейнера нет: он существует ради жеста. Высоту ему задают строки внутри,
   а разделители рисует сама строка. */
.task-subtree__item + .task-subtree__item,
.task-subtree > .task-subtree__item:first-child {
  border-top: 1px solid var(--border-soft);
}
</style>
