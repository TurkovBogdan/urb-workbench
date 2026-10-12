<script setup lang="ts">
// What an entity code stands for, as the hover card over its pill shows it: the code, the title
// and the description — or why there is nothing to show. One component for both zones, so a pill
// tells the same in the viewer and in the editor.
//
// It only reads the preview store; asking for the code is the body's job (`ensure` once the body is
// drawn), so a card that opens finds the record already there in the usual case. While it is not,
// a skeleton holds the card's place instead of an empty box.
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { IconAlertCircle } from '@tabler/icons-vue'
import { usePreviewStore } from '@/stores/preview'

const props = defineProps<{ code: string }>()

const { t, te } = useI18n()
const previews = usePreviewStore()

const record = computed(() => previews.get(props.code))

const missText = computed(() => {
  const error = record.value?.error
  if (!error) return ''
  const key = `common.editor.ref.preview.${error.code}`
  return te(key) ? t(key) : error.message
})
</script>

<template>
  <div class="ref-preview">
    <div class="ref-preview__code">{{ code }}</div>
    <template v-if="!record">
      <VSkeletonLoader type="text@2" class="ref-preview__skeleton" />
    </template>
    <div v-else-if="record.error" class="ref-preview__miss">
      <IconAlertCircle :size="15" :stroke-width="1.8" />
      <span>{{ missText }}</span>
    </div>
    <template v-else>
      <div class="ref-preview__title">{{ record.title }}</div>
      <div v-if="record.description" class="ref-preview__description">{{ record.description }}</div>
    </template>
  </div>
</template>

<style scoped>
.ref-preview {
  display: flex;
  flex-direction: column;
  gap: 4px;
  width: max-content;
  max-width: 360px;
  min-width: 220px;
  padding: 10px 12px;
}

.ref-preview__code {
  font-family: var(--font-mono, monospace);
  font-size: 0.75rem;
  color: rgba(var(--v-theme-on-surface), var(--v-medium-emphasis-opacity));
}

.ref-preview__title {
  font-size: 0.875rem;
  font-weight: 600;
  line-height: 1.35;
  overflow-wrap: anywhere;
}

.ref-preview__description {
  display: -webkit-box;
  -webkit-line-clamp: 4;
  -webkit-box-orient: vertical;
  overflow: hidden;
  font-size: 0.8125rem;
  line-height: 1.45;
  color: rgba(var(--v-theme-on-surface), var(--v-medium-emphasis-opacity));
  overflow-wrap: anywhere;
}

.ref-preview__miss {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 0.8125rem;
  color: rgba(var(--v-theme-on-surface), var(--v-medium-emphasis-opacity));
}

.ref-preview__skeleton {
  background: transparent;
}

.ref-preview__skeleton :deep(.v-skeleton-loader__text) {
  margin: 4px 0;
}
</style>
