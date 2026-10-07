<script setup lang="ts">
// Conflict dialog: a field the person was editing was changed in the database meanwhile.
//
// The decision is made for them in advance: the database wins — the agent has already written its
// version and relies on it, while the person knows what they changed. So the dialog asks nothing.
// It says what happened and hands back what the person typed so it is not lost silently: copy it
// and restore what is needed by hand. A full diff with a choice is the next step, not this one.
import { useI18n } from 'vue-i18n'

import CopyChip from '@/components/CopyChip.vue'

defineProps<{
  /** One per field: the field label and what the person had typed into it. */
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

/* The typed text as is, with all line breaks and markup: it is source the person will copy back,
   not text for reading. */
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
