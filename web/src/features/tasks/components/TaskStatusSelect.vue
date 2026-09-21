<script setup lang="ts">
/**
 * Выбор статуса: список со значками и две кнопки шага по ходу работы.
 *
 * Сделан по образцу `TaskPrioritySelect`: у статуса тоже есть порядок, и соседний берут чаще,
 * чем прыгают через весь набор — из плана в работу, из работы на проверку. Открывать список
 * ради шага на один пункт значит три движения вместо одного.
 *
 * Порядок — `TASK_STATUSES` как есть: очередь, план, работа, две проверки, два исхода. Он уже
 * читается слева направо ходом работы, поэтому разворачивать его, в отличие от приоритета,
 * не нужно. Края не заворачиваются: на «В очереди» гаснет левая кнопка, на «Отменено» правая.
 *
 * Всё оформление места применения (`label`, `variant`, `density`, `disabled`, `loading`)
 * проходит насквозь атрибутами: своей внешности у поля нет, она у страницы, где оно стоит.
 */
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

import VSelectStepper from '@/components/VSelectStepper.vue'
import { TASK_STATUSES, statusColor, statusIcon } from '../labels'

const model = defineModel<string>()

const { t } = useI18n()

const items = computed(() =>
  TASK_STATUSES.map((value) => ({ value, title: t(`tasks.task.status.${value}`) })),
)
</script>

<template>
  <!-- Значок берётся из значения пункта, а не из его собственного поля: `item` приезжает в слот
       в двух разных видах (исходный объект и обёртка Vuetify), а `value` и `title` есть у обоих. -->
  <VSelectStepper
    v-model="model"
    :items="items"
    :chips="false"
    :prev-label="t('tasks.task.status_step.back')"
    :next-label="t('tasks.task.status_step.forward')"
  >
    <template #item="{ props: itemProps, item }">
      <VListItem v-bind="itemProps">
        <template #prepend>
          <span class="status-select__glyph" :class="`status-select__glyph--${statusColor(item.value)}`">
            <component :is="statusIcon(item.value)" :size="16" :stroke-width="1.6" />
          </span>
        </template>
      </VListItem>
    </template>

    <!-- `#selection` работает только без чипов — с ними Vuetify рисует `#chip` и молча
         игнорирует этот слот. -->
    <template #selection="{ item }">
      <span class="status-select__line">
        <span class="status-select__glyph" :class="`status-select__glyph--${statusColor(item.value)}`">
          <component :is="statusIcon(item.value)" :size="16" :stroke-width="1.6" />
        </span>
        {{ item.title }}
      </span>
    </template>
  </VSelectStepper>
</template>

<style scoped>
/* Зазор значка и подписи тот же, что у пункта списка (`--v-list-prepend-gap`): выбранное
   значение — это тот же пункт, только показанный в поле, и разъехаться они не должны. */
.status-select__line {
  display: inline-flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
}

/* Цвета те же, что у глифа в строке списка задач: один статус не может быть зелёным в таблице
   и серым в поле, которым его меняют. */
.status-select__glyph {
  display: inline-flex;
  align-items: center;
  flex: none;
}

.status-select__glyph--accent  { color: var(--accent); }
.status-select__glyph--success { color: var(--success); }
.status-select__glyph--error   { color: var(--error); }
.status-select__glyph--warn    { color: var(--warn); }
.status-select__glyph--muted   { color: var(--text-faint); }
</style>
