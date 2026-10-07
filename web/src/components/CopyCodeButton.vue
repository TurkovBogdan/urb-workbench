<script setup lang="ts">
// "Grab the object code" — one button for every header: both on detail views (`DetailHead`) and on
// pages with a page-level header (the shelf's `PageHeader`). The markup used to live in
// `DetailHead`, and the shelf would have repeated it word for word — and such copies drift apart
// silently, one edit at a time.
//
// The label is required: the button sits next to the object's NAME, and a copy icon by itself
// doesn't say what it will grab. Where the code itself is on screen, it is copied with a chip
// (`CopyChip`) — text and icon as one button, and the "what gets copied" question doesn't arise.
import { useI18n } from 'vue-i18n'
import { IconCheck, IconCopy } from '@tabler/icons-vue'

import { useClipboard } from '@/composables/useClipboard'

defineProps<{
  code: string
}>()

const { t } = useI18n()
const { copy, isCopied } = useClipboard()
</script>

<template>
  <!-- Only the icon reports success: the label says what the button does and has no reason to
       change on press — otherwise the button briefly stops being the same one, and the whole row
       twitches with the label's length. -->
  <VBtn variant="text" @click="copy(code)">
    <template #prepend>
      <IconCheck v-if="isCopied(code)" :size="16" class="copy-code__done" />
      <IconCopy v-else :size="16" />
    </template>
    {{ t('common.action.copy_code') }}
  </VBtn>
</template>

<style scoped>
/* The icon change itself reports success, there's no need to name it with color: copying a code is a
   routine action done many times over, and a green flash in the header reads as an event. Grey keeps
   the check at the same weight as the icon it replaced. */
.copy-code__done {
  color: var(--text-muted);
}
</style>
