<script setup lang="ts">
// Окно конфликта: поле, которое человек правил, тем временем изменили в базе.
//
// Решение заранее принято за него: побеждает база — агент уже записал своё и на это
// рассчитывает, а человек знает, что сам менял. Поэтому окно ничего не спрашивает. Оно говорит,
// что случилось, и отдаёт набранное человеком, чтобы то не пропало молча: скопировать и
// вернуть нужное руками. Полный дифф с выбором — следующий шаг, а не этот.
import { useI18n } from 'vue-i18n'

import CopyChip from '@/components/CopyChip.vue'

defineProps<{
  /** По одному на поле: подпись поля и то, что человек успел в нём набрать. */
  items: { label: string; text: string }[]
}>()

const open = defineModel<boolean>({ required: true })

const { t } = useI18n()
</script>

<template>
  <VDialog v-model="open" max-width="640" scrollable>
    <VCard rounded="lg">
      <VCardTitle class="conflict__title">{{ t('tasks.task.conflict.title') }}</VCardTitle>
      <VCardText class="conflict__body">
        <p class="conflict__lead">{{ t('tasks.task.conflict.text') }}</p>

        <section v-for="(item, index) in items" :key="index" class="conflict__field">
          <div class="conflict__head">
            <span class="conflict__label">{{ item.label }}</span>
            <CopyChip :text="item.text" :label="t('tasks.task.conflict.copy')" />
          </div>
          <pre v-if="item.text" class="conflict__text">{{ item.text }}</pre>
          <p v-else class="conflict__empty">{{ t('tasks.task.conflict.empty') }}</p>
        </section>
      </VCardText>
      <VCardActions>
        <VSpacer />
        <VBtn color="primary" variant="flat" @click="open = false">{{ t('tasks.task.conflict.close') }}</VBtn>
      </VCardActions>
    </VCard>
  </VDialog>
</template>

<style scoped>
.conflict__title {
  font-size: 15px;
  font-weight: 600;
  white-space: normal;
}

.conflict__lead {
  margin: 0 0 14px;
  font-size: 13px;
  color: var(--text-muted);
}

.conflict__field + .conflict__field { margin-top: 14px; }

.conflict__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 6px;
}

.conflict__label {
  font-size: 12px;
  font-weight: 600;
  color: var(--text);
}

/* Набранное — как есть, со всеми переносами и разметкой: это исходник, который человек будет
   копировать обратно, а не текст для чтения. */
.conflict__text {
  margin: 0;
  max-height: 240px;
  overflow: auto;
  padding: 10px 12px;
  border: 1px solid var(--border-soft);
  border-radius: var(--radius-sm);
  background: var(--surface-hi);
  font-family: var(--font-mono);
  font-size: 12px;
  line-height: 1.5;
  white-space: pre-wrap;
  word-break: break-word;
}

.conflict__empty {
  margin: 0;
  font-size: 12px;
  color: var(--text-faint);
}
</style>
