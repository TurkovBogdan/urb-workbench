<script setup lang="ts">
// The passport of an uploaded archive: the root it carries, what is inside, where and when it was
// taken. The feature hands the title and the summary line; the rest is the archive's own.
import { useI18n } from 'vue-i18n'
import { IconPackage } from '@tabler/icons-vue'

import { fmtDateTime } from '@/shared/utils/date'
import { sizeText, type TransferArchive } from './types'

defineProps<{
  archive: TransferArchive
  title: string
  summary: string
  /** Where it came from beyond the installation: «из пространства «…»». */
  origin?: string
}>()

const { t, locale } = useI18n()
</script>

<template>
  <div class="transfer-passport">
    <div class="transfer-passport__title">{{ title }}</div>
    <div class="transfer-passport__summary">{{ summary }}</div>
    <div class="transfer-passport__facts">
      <span>
        {{ archive.same_install ? t('common.transfer.passport.same_install') : t('common.transfer.passport.other_install') }}<template v-if="origin">, {{ origin }}</template>
      </span>
      <span>{{ t('common.transfer.passport.created_at', { at: fmtDateTime(archive.created_at) }) }}</span>
      <span v-if="archive.app_version">{{ t('common.transfer.passport.version', { version: archive.app_version }) }}</span>
    </div>
    <div class="transfer-passport__file">
      <IconPackage :size="15" />
      <span class="transfer-passport__name">{{ archive.file_name }}</span>
      <span>{{ sizeText(archive.size, locale) }}</span>
    </div>
  </div>
</template>

<style scoped>
.transfer-passport {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.transfer-passport__title {
  font-size: 16px;
  font-weight: 600;
  line-height: 1.35;
  color: var(--text);
  overflow-wrap: anywhere;
}

.transfer-passport__summary {
  font-size: 13px;
  color: var(--text);
}

.transfer-passport__facts {
  display: flex;
  flex-wrap: wrap;
  gap: 2px 14px;
  font-size: 12px;
  color: var(--text-muted);
}

.transfer-passport__file {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: var(--text-faint);
}

.transfer-passport__name {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
