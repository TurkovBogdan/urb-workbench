<script setup lang="ts">
// Importing a knowledge base from a `.ucdx` archive: the file, the plan, the import, and whether to
// mount it into the current workspace.
//
// The archive carries no mounts — they are one installation's layout. The switch above the zone is
// their place here: on, the codex comes in mounted into the workspace the person works in; off, it
// waits in «Available» for whoever mounts it. A codex already mounted here keeps its mount.
//
// Conflicts are the codex and its records whose codes are taken here; a taken path is not one —
// the copy takes the next free one, and the plan says so before the button.
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'

import AppDialog from '@/components/AppDialog.vue'
import Callout from '@/components/Callout.vue'
import TransferConflicts from '@/components/transfer/TransferConflicts.vue'
import TransferDropZone from '@/components/transfer/TransferDropZone.vue'
import TransferNotices from '@/components/transfer/TransferNotices.vue'
import TransferPassport from '@/components/transfer/TransferPassport.vue'
import { sizeText, type TransferConflict } from '@/components/transfer/types'
import { useTransferImport } from '@/composables/useTransferImport'
import { pushToast } from '@/composables/useToasts'
import { useWorkspaceContextStore } from '@/features/workspace/stores/workspace-context.store'

import {
  analyzeCodexImport,
  applyCodexImport,
  cancelCodexImport,
  uploadCodexArchive,
  type CodexImportPlan,
  type CodexImportReport,
} from '../api'

const open = defineModel<boolean>({ required: true })

const props = defineProps<{
  /** The current workspace — where the codex is mounted if the person wants it; '' — none. */
  workspace: string
}>()

const emit = defineEmits<{ imported: [report: { code: string; mounted: boolean }] }>()

const { t, locale } = useI18n()
const context = useWorkspaceContextStore()

const EXTENSION = '.ucdx'

const mount = ref(true)
const workspaceTitle = computed(() => context.currentWorkspace?.title ?? '')

const flow = useTransferImport<CodexImportPlan, CodexImportReport>({
  upload: uploadCodexArchive,
  analyze: analyzeCodexImport,
  apply: (uploadId, decisions, planToken) =>
    applyCodexImport(uploadId, {
      workspace: mount.value && props.workspace ? props.workspace : null,
      decisions,
      plan_token: planToken,
    }),
  cancel: cancelCodexImport,
})

const { phase, plan, choices, error, progress, planChanged, ready, busy, fileName, fileSize } = flow

watch(open, (isOpen) => {
  if (isOpen) mount.value = Boolean(props.workspace)
  else void flow.discard()
}, { immediate: true })

const summary = computed(() => {
  const p = plan.value
  if (!p) return ''
  return [
    p.root.path,
    t('codex.transfer.summary.notes', p.counts.notes),
    t('codex.transfer.summary.deleted', p.counts.deleted_notes),
    t('codex.transfer.summary.files', p.counts.files),
  ].join(' · ')
})

function entityLabel(entity: string): string {
  return t(`codex.transfer.entity.${entity}`)
}

function reasonText(conflict: TransferConflict): string {
  return conflict.reason ? t(`codex.transfer.reason.${conflict.reason}`, conflict.reason_params) : ''
}

function describe(conflict: TransferConflict): string {
  const local = conflict.local
  const deleted = local.deleted ? ` ${t('codex.transfer.local.deleted')}` : ''
  if (local.kind === 'codex') return t('codex.transfer.local.codex', { title: local.title, path: local.path ?? '' }) + deleted
  if (local.kind === 'record') {
    return local.holder_title
      ? t('codex.transfer.local.record', { title: local.title, codex: local.holder_title }) + deleted
      : t('codex.transfer.local.record_alone', { title: local.title }) + deleted
  }
  return t('codex.transfer.local.file', { size: sizeText(conflict.dates.local.size, locale.value) })
}

const notices = computed(() => {
  const p = plan.value
  if (!p) return []
  // The copy a «replace» brings cannot take the path the codex here holds: it gets the next free one.
  // The copy moves only off a path a live codex here holds: a codex here in the bin holds none, a
  // record holding the code holds no codex path, a copy coming in the bin needs none.
  const copied = choices.value[p.root.code] === 'replace'
    && !p.root.deleted
    && p.conflicts.some((c) => c.id === p.root.code && c.local.kind === 'codex' && !c.local.deleted)
    && !p.notices.repathed.some((row) => row.entity === 'codex')
    ? [`${p.root.title}: ${p.root.path} → ${t('codex.transfer.notice.free_path')}`]
    : []
  return [
    {
      key: 'repathed',
      title: t('codex.transfer.notice.repathed'),
      lines: [
        ...p.notices.repathed.map((row) => `${row.title}: ${row.from} → ${row.to || t('codex.transfer.notice.free_path')}`),
        ...copied,
      ],
    },
    {
      key: 'recoded',
      title: t('codex.transfer.notice.recoded'),
      lines: p.notices.recoded.map((row) => `${entityLabel(row.entity)}: ${row.title || row.from} — ${row.from} → ${row.to}`),
    },
    { key: 'dangling', title: t('codex.transfer.notice.dangling'), lines: p.notices.dangling_refs },
  ]
})

async function apply(): Promise<void> {
  const report = await flow.apply()
  if (!report) return
  open.value = false
  pushToast(t('codex.transfer.done', { title: report.codex.title }), 'success')
  emit('imported', { code: report.codex.code, mounted: report.mounted })
}
</script>

<template>
  <AppDialog
    v-model="open"
    :title="t('codex.transfer.title')"
    :description="t('codex.transfer.description')"
    size="base"
    scrollable
    :persistent="busy"
    :close-disabled="busy"
  >
    <div class="codex-import">
      <VSwitch
        v-if="workspace"
        v-model="mount"
        :label="t('codex.transfer.mount', { workspace: workspaceTitle })"
        :disabled="phase === 'apply'"
        color="primary"
        density="compact"
        hide-details
      />
      <Callout v-else tone="muted">{{ t('codex.transfer.no_workspace') }}</Callout>

      <template v-if="phase === 'pick'">
        <TransferDropZone :extension="EXTENSION" :lead="t('codex.transfer.drop_lead')" @file="flow.start" />
        <VAlert v-if="error" type="error" variant="tonal" density="compact">{{ error }}</VAlert>
      </template>

      <div v-else-if="phase === 'upload' || phase === 'analyze'" class="codex-import__reading">
        <div class="codex-import__file">{{ fileName }} · {{ sizeText(fileSize, locale) }}</div>
        <VProgressLinear
          :model-value="phase === 'upload' ? progress : undefined"
          :indeterminate="phase === 'analyze'"
          color="primary"
          rounded
        />
        <div class="codex-import__step">
          {{ phase === 'upload' ? t('common.transfer.step.upload', { percent: progress }) : t('common.transfer.step.analyze') }}
        </div>
      </div>

      <template v-else-if="plan">
        <TransferPassport :archive="plan.archive" :title="plan.root.title" :summary="summary" />

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
        <Callout v-else tone="muted">{{ t('codex.transfer.no_conflicts') }}</Callout>

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
.codex-import {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.codex-import__reading {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 12px 0;
}

.codex-import__file {
  font-size: 14px;
  color: var(--text);
  overflow-wrap: anywhere;
}

.codex-import__step {
  font-size: 12px;
  color: var(--text-muted);
}
</style>
