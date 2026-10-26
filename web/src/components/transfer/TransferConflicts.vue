<script setup lang="ts">
// The conflicts of an import: each entity whose code is taken here, with what holds it, the dates
// of both sides — the fresher one marked — and the person's choice.
//
// A choice that is not possible is not hidden: it stands disabled with its reason under the title,
// so the person sees why the archive's note can only come in as a new one. Choosing «replace» for a
// task turns its notes' «update» into «replace» by itself — the rules live in `types.ts`, the same
// ones the server checks.
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

import { fmtDateTime } from '@/shared/utils/date'

import { canUpdate, sizeText, type TransferChoice, type TransferConflict, type TransferSide } from './types'

const props = defineProps<{
  conflicts: TransferConflict[]
  choices: Record<string, TransferChoice>
  /** The feature's word for an entity kind. */
  entityLabel: (entity: string) => string
  /** Why «update» is not offered, in the feature's words; '' when it is. */
  reasonText: (conflict: TransferConflict) => string
  /** What holds the code here, one line. */
  describe: (conflict: TransferConflict) => string
  disabled?: boolean
}>()

const emit = defineEmits<{
  choose: [id: string, value: TransferChoice]
  chooseAll: [value: TransferChoice]
}>()

const { t, locale } = useI18n()

const choosable = computed(() => props.conflicts.some((conflict) => conflict.options.length > 1))

// The archive's moments are written as the API writes them, so two of them compare as strings.
function fresher(conflict: TransferConflict): 'local' | 'archive' | null {
  const here = conflict.dates.local.updated_at ?? conflict.dates.local.created_at
  const there = conflict.dates.archive.updated_at ?? conflict.dates.archive.created_at
  if (!here || !there || here === there) return null
  return here > there ? 'local' : 'archive'
}

function sideText(side: TransferSide, isFile: boolean): string {
  const parts: string[] = []
  if (side.updated_at) parts.push(t('common.transfer.conflict.changed', { at: fmtDateTime(side.updated_at) }))
  else if (side.created_at) parts.push(t('common.transfer.conflict.appeared', { at: fmtDateTime(side.created_at) }))
  if (isFile && side.updated_at && side.created_at) {
    parts.push(t('common.transfer.conflict.appeared', { at: fmtDateTime(side.created_at) }))
  }
  if (side.size !== null && side.size !== undefined) parts.push(sizeText(side.size, locale.value))
  return parts.join(' · ') || t('common.transfer.conflict.no_date')
}

function updateDisabled(conflict: TransferConflict): boolean {
  return props.disabled || !canUpdate(conflict, props.choices)
}

function hint(conflict: TransferConflict): string {
  const reason = props.reasonText(conflict)
  if (reason) return reason
  if (conflict.requires && !canUpdate(conflict, props.choices)) {
    return t('common.transfer.conflict.follows', { code: conflict.requires.id })
  }
  return ''
}
</script>

<template>
  <div class="transfer-conflicts">
    <div class="transfer-conflicts__head">
      <span class="transfer-conflicts__count">{{ t('common.transfer.conflict.count', conflicts.length) }}</span>
      <div v-if="choosable" class="transfer-conflicts__all">
        <VBtn size="small" variant="text" :disabled="disabled" @click="emit('chooseAll', 'update')">
          {{ t('common.transfer.conflict.update_all') }}
        </VBtn>
        <VBtn size="small" variant="text" :disabled="disabled" @click="emit('chooseAll', 'replace')">
          {{ t('common.transfer.conflict.replace_all') }}
        </VBtn>
      </div>
    </div>

    <ul class="transfer-conflicts__list">
      <li v-for="conflict in conflicts" :key="conflict.id" class="transfer-conflict">
        <div class="transfer-conflict__text">
          <div class="transfer-conflict__title">
            <span class="transfer-conflict__entity">{{ entityLabel(conflict.entity) }}</span>
            {{ conflict.title }}
            <code class="transfer-conflict__code">{{ conflict.id }}</code>
          </div>
          <div class="transfer-conflict__here">{{ describe(conflict) }}</div>
          <div class="transfer-conflict__dates">
            <span :class="{ 'transfer-conflict__date--fresher': fresher(conflict) === 'local' }">
              {{ t('common.transfer.conflict.here') }}: {{ sideText(conflict.dates.local, conflict.entity === 'file') }}
            </span>
            <span :class="{ 'transfer-conflict__date--fresher': fresher(conflict) === 'archive' }">
              {{ t('common.transfer.conflict.archive') }}: {{ sideText(conflict.dates.archive, conflict.entity === 'file') }}
            </span>
          </div>
          <div v-if="hint(conflict)" class="transfer-conflict__reason">{{ hint(conflict) }}</div>
        </div>

        <VBtnToggle
          :model-value="choices[conflict.id]"
          density="compact"
          variant="outlined"
          divided
          class="transfer-conflict__choice"
          @update:model-value="(value: TransferChoice) => value && emit('choose', conflict.id, value)"
        >
          <VBtn value="update" size="small" :disabled="updateDisabled(conflict)">
            {{ t('common.transfer.choice.update') }}
          </VBtn>
          <VBtn value="replace" size="small" :disabled="disabled">
            {{ t('common.transfer.choice.replace') }}
          </VBtn>
        </VBtnToggle>
      </li>
    </ul>
  </div>
</template>

<style scoped>
.transfer-conflicts__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 6px;
}

.transfer-conflicts__count {
  font-size: 13px;
  font-weight: 600;
  color: var(--text);
}

.transfer-conflicts__all {
  display: flex;
  gap: 4px;
}

.transfer-conflicts__list {
  display: flex;
  flex-direction: column;
  margin: 0;
  padding: 0;
  list-style: none;
  border: 1px solid var(--border);
  border-radius: var(--radius);
}

.transfer-conflict {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  padding: 10px 12px;
}

.transfer-conflict + .transfer-conflict {
  border-top: 1px solid var(--border);
}

.transfer-conflict__text {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.transfer-conflict__title {
  font-size: 14px;
  color: var(--text);
  overflow-wrap: anywhere;
}

.transfer-conflict__entity {
  margin-right: 6px;
  font-size: 12px;
  color: var(--text-faint);
}

.transfer-conflict__code {
  margin-left: 6px;
  font-family: var(--font-mono);
  font-size: 11px;
  color: var(--text-faint);
}

.transfer-conflict__here,
.transfer-conflict__reason {
  font-size: 12px;
  color: var(--text-muted);
}

.transfer-conflict__reason {
  color: var(--warn);
}

.transfer-conflict__dates {
  display: flex;
  flex-wrap: wrap;
  gap: 2px 14px;
  font-size: 12px;
  color: var(--text-faint);
}

/* The fresher side reads first: it is what the person compares. */
.transfer-conflict__date--fresher {
  color: var(--text);
  font-weight: 600;
}

.transfer-conflict__choice {
  flex: none;
}
</style>
