<script setup lang="ts">
// Importing a task from a `.utsk` archive: the group it lands in, the file, the plan, the import.
//
// One window for the whole path: the archive waits on the server between the steps, so leaving the
// window half way gives it back (`discard`) instead of abandoning it there. The group is asked
// first and stays above — the archive carries no group, and a subtask follows its root into it.
//
// Conflicts are the archive's tasks and notes whose codes are taken here; each is chosen by the
// person — «update» writes the archive over, «replace» brings a new one under a new code.
import { computed, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'

import AppDialog from '@/components/AppDialog.vue'
import Callout from '@/components/Callout.vue'
import IconSwatch from '@/components/IconSwatch.vue'
import VSelectSearch from '@/components/VSelectSearch.vue'
import TransferConflicts from '@/components/transfer/TransferConflicts.vue'
import TransferDropZone from '@/components/transfer/TransferDropZone.vue'
import TransferNotices from '@/components/transfer/TransferNotices.vue'
import TransferPassport from '@/components/transfer/TransferPassport.vue'
import { sizeText, type TransferConflict } from '@/components/transfer/types'
import { useTransferImport } from '@/composables/useTransferImport'
import { pushToast } from '@/composables/useToasts'

import {
  analyzeTaskImport,
  applyTaskImport,
  cancelTaskImport,
  listGroups,
  uploadTaskArchive,
  type GroupRow,
  type TaskImportPlan,
  type TaskImportReport,
} from '../api'

const open = defineModel<boolean>({ required: true })

const props = defineProps<{
  /** The workspace the task is imported into. */
  workspace: string
}>()

const emit = defineEmits<{ imported: [code: string] }>()

const { t, locale } = useI18n()
const router = useRouter()

const EXTENSION = '.utsk'

const groupCode = ref<string | null>(null)
const groups = ref<GroupRow[]>([])

const groupItems = computed(() =>
  groups.value.map((group) => ({ value: group.code, title: group.title, icon: group.icon, color: group.color })),
)

const flow = useTransferImport<TaskImportPlan, TaskImportReport>({
  upload: uploadTaskArchive,
  analyze: (uploadId) => analyzeTaskImport(uploadId, props.workspace),
  apply: (uploadId, decisions, planToken) =>
    applyTaskImport(uploadId, { workspace: props.workspace, group_code: groupCode.value, decisions, plan_token: planToken }),
  cancel: cancelTaskImport,
})

const { phase, plan, choices, error, progress, planChanged, ready, busy, fileName, fileSize } = flow

async function loadGroups(): Promise<void> {
  try {
    groups.value = props.workspace ? await listGroups({ workspace: props.workspace }, { report: false }) : []
  } catch {
    groups.value = []
  }
}

watch(open, (isOpen) => {
  if (isOpen) {
    groupCode.value = null
    void loadGroups()
  } else {
    void flow.discard()
  }
}, { immediate: true })

const summary = computed(() => {
  const p = plan.value
  if (!p) return ''
  return [
    t('tasks.transfer.summary.subtasks', p.root.subtasks),
    t('tasks.transfer.summary.stages', p.counts.stages),
    t('tasks.transfer.summary.journal', p.counts.journal),
    t('tasks.transfer.summary.notes', p.counts.notes),
    t('tasks.transfer.summary.files', p.counts.files),
  ].join(' · ')
})

const origin = computed(() =>
  plan.value?.archive.source_workspace
    ? t('tasks.transfer.origin', { workspace: plan.value.archive.source_workspace })
    : '',
)

function entityLabel(entity: string): string {
  return t(`tasks.transfer.entity.${entity}`)
}

function reasonText(conflict: TransferConflict): string {
  return conflict.reason ? t(`tasks.transfer.reason.${conflict.reason}`, conflict.reason_params) : ''
}

function describe(conflict: TransferConflict): string {
  const local = conflict.local
  const deleted = local.deleted ? ` ${t('tasks.transfer.local.deleted')}` : ''
  if (local.kind === 'task') {
    return t('tasks.transfer.local.task', { title: local.title, workspace: local.workspace }) + deleted
  }
  if (local.kind === 'note') {
    return local.holder
      ? t('tasks.transfer.local.note', { title: local.title, task: local.holder_title || local.holder }) + deleted
      : t('tasks.transfer.local.note_alone', { title: local.title }) + deleted
  }
  return t('tasks.transfer.local.file', { size: sizeText(conflict.dates.local.size, locale.value) })
}

const notices = computed(() => {
  const p = plan.value
  if (!p) return []
  return [
    {
      key: 'recoded',
      title: t('tasks.transfer.notice.recoded'),
      lines: p.notices.recoded.map((row) =>
        `${entityLabel(row.entity)}: ${row.title || row.from} — ${row.from} → ${row.to || t('tasks.transfer.notice.new_code')}`),
    },
    { key: 'dangling', title: t('tasks.transfer.notice.dangling'), lines: p.notices.dangling_refs },
  ]
})

async function apply(): Promise<void> {
  const report = await flow.apply()
  if (!report) return
  open.value = false
  pushToast(t('tasks.transfer.done', { title: report.task.title }), 'success')
  emit('imported', report.task.code)
  void router.push(`/tasks/task/${encodeURIComponent(report.task.code)}`)
}
</script>

<template>
  <AppDialog
    v-model="open"
    :title="t('tasks.transfer.title')"
    :description="t('tasks.transfer.description')"
    size="base"
    scrollable
    :persistent="busy"
    :close-disabled="busy"
  >
    <div class="task-import">
      <VSelectSearch
        v-model="groupCode"
        :items="groupItems"
        :label="t('tasks.transfer.group')"
        :placeholder="t('tasks.transfer.no_group')"
        persistent-placeholder
        :search-placeholder="t('tasks.task.detail.group_search')"
        :no-data-text="t('tasks.task.detail.group_empty')"
        :chips="false"
        :disabled="phase === 'apply'"
        variant="outlined"
        density="compact"
        clearable
        hide-details
      >
        <template #item="{ props: itemProps, item }">
          <VListItem v-bind="itemProps">
            <template #prepend>
              <IconSwatch :icon="item.icon" :color="item.color" :width="20" />
            </template>
          </VListItem>
        </template>
        <template #selection="{ item }">
          <span class="task-import__group">
            <IconSwatch :icon="item.icon ?? ''" :color="item.color ?? ''" :width="20" />
            {{ item.title }}
          </span>
        </template>
      </VSelectSearch>

      <template v-if="phase === 'pick'">
        <TransferDropZone :extension="EXTENSION" :lead="t('tasks.transfer.drop_lead')" @file="flow.start" />
        <VAlert v-if="error" type="error" variant="tonal" density="compact">{{ error }}</VAlert>
      </template>

      <div v-else-if="phase === 'upload' || phase === 'analyze'" class="task-import__reading">
        <div class="task-import__file">{{ fileName }} · {{ sizeText(fileSize, locale) }}</div>
        <VProgressLinear
          :model-value="phase === 'upload' ? progress : undefined"
          :indeterminate="phase === 'analyze'"
          color="primary"
          rounded
        />
        <div class="task-import__step">
          {{ phase === 'upload' ? t('common.transfer.step.upload', { percent: progress }) : t('common.transfer.step.analyze') }}
        </div>
      </div>

      <template v-else-if="plan">
        <TransferPassport :archive="plan.archive" :title="plan.root.title" :summary="summary" :origin="origin" />

        <Callout v-if="planChanged" tone="warn">{{ t('common.transfer.plan_changed') }}</Callout>

        <TransferConflicts
          v-if="plan.conflicts.length"
          :conflicts="plan.conflicts"
          :choices="choices"
          :entity-label="entityLabel"
          :reason-text="reasonText"
          :describe="describe"
          :disabled="phase === 'apply'"
          @choose="flow.pick"
          @choose-all="flow.pickAll"
        />
        <Callout v-else tone="muted">{{ t('tasks.transfer.no_conflicts') }}</Callout>

        <TransferNotices :buckets="notices" />

        <VAlert v-if="error" type="error" variant="tonal" density="compact">{{ error }}</VAlert>

        <div>
          <VBtn variant="text" size="small" :disabled="phase === 'apply'" @click="flow.discard">
            {{ t('common.transfer.another_file') }}
          </VBtn>
        </div>
      </template>
    </div>

    <template #actions>
      <VBtn variant="text" :disabled="phase === 'apply'" @click="open = false">
        {{ t('common.action.cancel') }}
      </VBtn>
      <VBtn color="primary" variant="flat" :disabled="!ready" :loading="phase === 'apply'" @click="apply">
        {{ t('common.transfer.import') }}
      </VBtn>
    </template>
  </AppDialog>
</template>

<style scoped>
.task-import {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.task-import__group {
  display: inline-flex;
  align-items: center;
  gap: 8px;
}

.task-import__reading {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 12px 0;
}

.task-import__file {
  font-size: 14px;
  color: var(--text);
  overflow-wrap: anywhere;
}

.task-import__step {
  font-size: 12px;
  color: var(--text-muted);
}
</style>
