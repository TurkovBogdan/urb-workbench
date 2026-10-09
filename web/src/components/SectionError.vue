<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { IconAlertTriangle, IconSearchOff } from '@tabler/icons-vue'
import { ApiError } from '@/api/client/internal'
import { errorText } from '@/api/errorText'

// A failure to READ a section: the entity doesn't exist, the list didn't load. No full-shell screen
// here — navigation is alive, the person came to a valid address, and the menu and header must stay.
// Shown in place of the content: why it's empty and what to do next.
//
// An OPERATION failure never lands here — it surfaces as a message next to the action.

const props = defineProps<{ error: unknown }>()

const { t } = useI18n()

const missing = computed(() => props.error instanceof ApiError && props.error.status === 404)

// The title is generic; the subject noun comes with the backend response itself ("Research not
// found") — it is printed on the line below, so there's no point duplicating it with a prop.
const title = computed(() => (
  missing.value ? t('common.errors.section.missing') : t('common.errors.section.failed')
))
</script>

<template>
  <div class="section-error" role="alert" aria-live="polite">
    <component
      :is="missing ? IconSearchOff : IconAlertTriangle"
      class="section-error__icon"
      :size="40"
      stroke="1.5"
    />
    <p class="section-error__title">{{ title }}</p>
    <p class="section-error__text">{{ errorText(error) }}</p>
    <slot name="actions" />
  </div>
</template>

<style scoped>
.section-error {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 6px;
  text-align: center;
  padding: 48px 24px;
}

.section-error__icon {
  color: var(--text-faint);
  margin-bottom: 6px;
}

.section-error__title {
  margin: 0;
  font-size: 15px;
  font-weight: 600;
  color: var(--text);
}

.section-error__text {
  margin: 0;
  max-width: 420px;
  font-size: 13px;
  color: var(--text-muted);
}
</style>
