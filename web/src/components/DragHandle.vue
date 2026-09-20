<script setup lang="ts">
// Ручка перетаскивания — одна на всё приложение.
//
// Одна намеренно: размер зоны хвата, гашение ripple, `touch-action`, кольцо фокуса и подпись для
// читалки задаются здесь, а место применения отличается только селектором в `handle` у sortable.
// Разъехавшись, эти пять вещей дают пять разных ручек, из которых работает одна.
//
// ЗАЧЕМ РУЧКА ВООБЩЕ. Без неё перетаскивается вся строка, и тогда у строки отнимается выделение
// текста, а на тач-устройстве — прокрутка: жест начинается с того же движения. Ручка разводит
// «взять» и «прокрутить» по разным местам строки.
//
// `touch-action: none` обязателен и стоит ровно на ручке: браузер иначе съедает pointer-события
// в пользу собственной прокрутки, и жест не начинается. Ставить его на строку целиком нельзя —
// тогда список перестанет прокручиваться пальцем.
import { IconGripVertical } from '@tabler/icons-vue'

withDefaults(defineProps<{
  /** Подпись для читалки: что именно эта ручка двигает. */
  label: string
  /** Ручка видна всегда, а не только под курсором строки. */
  always?: boolean
}>(), {
  always: false,
})
</script>

<template>
  <span
    class="drag-handle"
    :class="{ 'drag-handle--always': always }"
    role="button"
    tabindex="-1"
    :aria-label="label"
    :title="label"
  >
    <IconGripVertical :size="14" :stroke-width="1.8" />
  </span>
</template>

<style scoped>
/* Коробка шире значка: хватать приходится точно, и 14px глифа — это не зона хвата. Ширина взята
   по высоте плотной строки списка, чтобы ручка не растила её собой. */
.drag-handle {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 20px;
  height: 28px;
  flex: none;
  color: var(--text-faint);
  cursor: grab;
  opacity: 0;
  transition: opacity 0.12s ease, color 0.12s ease;
  touch-action: none;
  user-select: none;
}

.drag-handle--always,
.drag-handle:focus-visible { opacity: 1; }

/* Появляется по наведению на СТРОКУ, а не на себя: невидимую ручку курсором не найти. */
:where(.task-row, .drag-row):hover .drag-handle { opacity: 1; }

.drag-handle:hover { color: var(--text); }

.drag-handle:active { cursor: grabbing; }

/* Палец на тач-устройстве не наводится: там ручка видна всегда, иначе её нечем вызвать. */
@media (hover: none) {
  .drag-handle { opacity: 1; }
}
</style>
