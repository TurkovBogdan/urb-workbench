<script setup lang="ts">
/**
 * Выбор приоритета: список со значками и две кнопки шага по лестнице важности.
 *
 * Отдельный компонент, потому что мест выбора уже два — карточка задачи и форма заведения, — а
 * пункт приоритета не голая строка: порядок, значок и цвет живут в `labels.ts`, и собирать их в
 * каждом окне заново значило бы разойтись на первой же правке справочника.
 *
 * Кнопки — `VSelectStepper` дизайн-системы: приоритет это лестница, и соседнюю ступень берут
 * чаще, чем прыгают через весь набор. Набор развёрнут от замороженного к горящему — обратно
 * `TASK_PRIORITIES`, где первым идёт самое важное: шкалу читают снизу вверх, и тогда движение
 * вправо совпадает с ростом важности, как на любом ползунке. Края не заворачиваются — на
 * замороженном гаснет левая кнопка, на горящем правая.
 *
 * Всё оформление места применения (`label`, `variant`, `density`, `disabled`) проходит насквозь
 * атрибутами: своей внешности у поля нет, она у окна, где оно стоит.
 */
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

import VSelectStepper from '@/components/VSelectStepper.vue'
import { TASK_PRIORITIES, priorityColor, priorityIcon } from '../labels'

const model = defineModel<string>()

const { t } = useI18n()

// Копия перед разворотом обязательна: `TASK_PRIORITIES` — общий справочник, и `reverse` на нём
// самом перевернул бы порядок и в фильтрах, и везде, где его читают.
const items = computed(() =>
  [...TASK_PRIORITIES]
    .reverse()
    .map((value) => ({ value, title: t(`tasks.task.priority.${value}`) })),
)
</script>

<template>
  <!-- Значок берётся из значения пункта, а не из его собственного поля: `item` приезжает в слот
       в двух разных видах (исходный объект и обёртка Vuetify), а `value` и `title` есть у обоих. -->
  <VSelectStepper
    v-model="model"
    :items="items"
    :chips="false"
    :prev-label="t('tasks.task.priority_step.lower')"
    :next-label="t('tasks.task.priority_step.raise')"
  >
    <template #item="{ props: itemProps, item }">
      <VListItem v-bind="itemProps">
        <template #prepend>
          <span class="priority-select__glyph" :class="`priority-select__glyph--${priorityColor(item.value)}`">
            <component :is="priorityIcon(item.value)" :size="16" :stroke-width="1.6" />
          </span>
        </template>
      </VListItem>
    </template>

    <!-- `#selection` работает только без чипов — с ними Vuetify рисует `#chip` и молча
         игнорирует этот слот. -->
    <template #selection="{ item }">
      <span class="priority-select__line">
        <span class="priority-select__glyph" :class="`priority-select__glyph--${priorityColor(item.value)}`">
          <component :is="priorityIcon(item.value)" :size="16" :stroke-width="1.6" />
        </span>
        {{ item.title }}
      </span>
    </template>
  </VSelectStepper>
</template>

<style scoped>
/* Зазор значка и подписи тот же, что у пункта списка (`--v-list-prepend-gap`): выбранное
   значение — это тот же пункт, только показанный в поле, и разъехаться они не должны. */
.priority-select__line {
  display: inline-flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
}

/* Цвета те же, что у глифа в строке списка задач: один приоритет не может быть красным на
   карточке и серым в поле, которым его меняют. */
.priority-select__glyph {
  display: inline-flex;
  align-items: center;
  flex: none;
}

.priority-select__glyph--accent  { color: var(--accent); }
.priority-select__glyph--success { color: var(--success); }
.priority-select__glyph--error   { color: var(--error); }
.priority-select__glyph--warn    { color: var(--warn); }
.priority-select__glyph--muted   { color: var(--text-faint); }
</style>
