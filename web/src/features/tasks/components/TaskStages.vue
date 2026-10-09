<script setup lang="ts">
// Plan stages: the board of a task's steps, each with its own state and evidence of completion.
//
// Edited in place, like the whole detail page: a row expands, fields are sent on leaving them.
// There is no save button — the task itself has none either, and a second way of working on one
// page would read as a bug.
//
// A STAGE CANNOT BE CLOSED WITHOUT EVIDENCE — this is a backend rule, and the UI does not duplicate
// it with a check but shows it: while `evidence` is empty, the "Done" button is locked and explains
// why. Were we to duplicate the check here, one rule would live in two places, and they would
// diverge on day one.
import { computed, reactive, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { IconChevronRight, IconTrash } from '@tabler/icons-vue'

import ConfirmDialog from '@/components/ConfirmDialog.vue'
import { MarkdownEditor } from '@/components/markdown/editor'
import { errorText } from '@/api/errorText'

import {
  createStage,
  deleteStage,
  setStageStatus,
  updateStage,
  type StageRow,
} from '../api'
import { TASK_BRIEF_FEATURES, TASK_DOCUMENT_FEATURES } from '../editor'
import CollectionHeader from './CollectionHeader.vue'
import {
  BODY_MAX,
  STAGE_EVIDENCE_MAX,
  TASK_DESCRIPTION_MAX,
  TASK_STATUSES,
  TASK_TITLE_MAX,
  statusIcon,
} from '../labels'

const props = defineProps<{
  taskCode: string
  stages: StageRow[]
  /** The task is in the trash: nothing to edit, shown as is. */
  disabled?: boolean
}>()

const emit = defineEmits<{ changed: [] }>()

const { t } = useI18n()

const open = ref<string | null>(null)
const busy = ref(false)
const error = ref<string | null>(null)
const removing = ref<StageRow | null>(null)
const removeOpen = ref(false)

const statusItems = computed(() =>
  TASK_STATUSES.map((value) => ({ value, title: t(`tasks.task.status.${value}`) })),
)

/** Expand a row or collapse the same one: a second click on the open row closes it. */
function toggle(code: string) {
  open.value = open.value === code ? null : code
}

async function run(action: () => Promise<unknown>) {
  busy.value = true
  error.value = null
  try {
    await action()
    emit('changed')
  } catch (e) {
    error.value = errorText(e)
  } finally {
    busy.value = false
  }
}

async function add() {
  await run(async () => {
    const stage = await createStage(
      props.taskCode,
      { title: t('tasks.stage.new_title'), description: '', body: '' },
      { report: false },
    )
    open.value = stage.code
  })
}

// ── Typed but not yet sent ────────────────────────────────────────────────────
// Fields are sent on leaving them, but the markdown editor delivers its value via an event, it is
// not in the DOM: there is nowhere to read it from at blur time, as with `VTextarea`. So the last
// typed value accumulates here per "stage + field" pair, and blur picks it up.
type MarkdownField = 'description' | 'body' | 'evidence'

const pending = reactive<Record<string, Partial<Record<MarkdownField, string>>>>({})

function stash(stage: StageRow, field: MarkdownField, value: string): void {
  ;(pending[stage.code] ??= {})[field] = value
}

function flush(stage: StageRow, field: MarkdownField): void {
  const value = pending[stage.code]?.[field]
  delete pending[stage.code]?.[field]
  // Unchanged values are not sent: leaving a field where nothing was typed must not look like an
  // edit — neither in the change log nor in the task's update time.
  if (value === undefined || value === stage[field]) return
  void patch(stage, { [field]: value })
}

function patch(stage: StageRow, fields: Partial<Pick<StageRow, 'title' | 'description' | 'body' | 'evidence'>>) {
  return run(() =>
    updateStage(
      stage.code,
      {
        title: fields.title ?? stage.title,
        description: fields.description ?? stage.description,
        body: fields.body ?? stage.body,
        evidence: fields.evidence ?? stage.evidence,
      },
      { report: false },
    ),
  )
}

function changeStatus(stage: StageRow, status: string) {
  return run(() => setStageStatus(stage.code, status, { report: false }))
}

function askRemove(stage: StageRow) {
  removing.value = stage
  removeOpen.value = true
}

async function remove() {
  const stage = removing.value
  if (!stage) return
  await run(() => deleteStage(stage.code, { report: false }))
  removeOpen.value = false
}
</script>

<template>
  <section class="stages">
    <CollectionHeader
      :title="t('tasks.stage.section')"
      :hint="t('tasks.stage.hint')"
      :add-label="props.disabled ? undefined : t('tasks.stage.add')"
      :adding="busy"
      :empty="!props.stages.length && !error"
      class="stages__header"
      @add="add"
    />

    <VAlert v-if="error" type="error" variant="tonal" density="compact" class="stages__error">
      {{ error }}
    </VAlert>

    <div v-for="stage in props.stages" :key="stage.code" class="stage" :class="{ 'stage--open': open === stage.code }">
      <!-- A collapsed row answers three questions at once: which number, in what state and about
           what. It is expanded for editing and evidence — that is, rarely. -->
      <button type="button" class="stage__head" @click="toggle(stage.code)">
        <IconChevronRight :size="14" :stroke-width="1.8" class="stage__chevron" />
        <span class="stage__number">{{ stage.number }}</span>
        <component :is="statusIcon(stage.status)" :size="16" :stroke-width="1.6" class="stage__status" />
        <span class="stage__title">{{ stage.title }}</span>
        <span v-if="stage.evidence" class="stage__evidence-mark">{{ t('tasks.stage.has_evidence') }}</span>
      </button>

      <div v-if="open === stage.code" class="stage__body">
        <VTextField
          :model-value="stage.title"
          :label="t('tasks.stage.title')"
          :maxlength="TASK_TITLE_MAX"
          :disabled="props.disabled || busy"
          variant="outlined"
          density="compact"
          hide-details
          @blur="(event: FocusEvent) => patch(stage, { title: (event.target as HTMLInputElement).value })"
        />

        <!-- A stage goal is a phrase, hence simple mode: a heading or table has no place in it, and
             the schema does not know them. -->
        <MarkdownEditor
          :model-value="stage.description"
          :label="t('tasks.stage.description')"
          :max-length="TASK_DESCRIPTION_MAX"
          :readonly="props.disabled || busy"
          mode="simple"
          min-height="0"
          @update:model-value="(value) => stash(stage, 'description', value)"
          @blur="flush(stage, 'description')"
        />

        <!-- A stage body is the same kind of document as the task plan: one step of it. -->
        <MarkdownEditor
          :model-value="stage.body"
          :label="t('tasks.stage.body')"
          :max-length="BODY_MAX"
          :readonly="props.disabled || busy"
          :features="TASK_DOCUMENT_FEATURES"
          min-height="0"
          @update:model-value="(value) => stash(stage, 'body', value)"
          @blur="flush(stage, 'body')"
        />

        <!-- Evidence is a pointer, not a story: the hint under the field says what goes here,
             because the field name does not reveal it. Hence the feature set: a list with inline
             markup, no sections or tables. -->
        <MarkdownEditor
          :model-value="stage.evidence"
          :label="t('tasks.stage.evidence')"
          :hint="t('tasks.stage.evidence_hint')"
          :max-length="STAGE_EVIDENCE_MAX"
          :readonly="props.disabled || busy"
          :features="TASK_BRIEF_FEATURES"
          min-height="0"
          @update:model-value="(value) => stash(stage, 'evidence', value)"
          @blur="flush(stage, 'evidence')"
        />

        <div class="stage__actions">
          <VSelect
            :model-value="stage.status"
            :items="statusItems"
            :label="t('tasks.stage.status')"
            :disabled="props.disabled || busy"
            variant="outlined"
            density="compact"
            hide-details
            class="stage__status-select"
            @update:model-value="(value) => changeStatus(stage, value as string)"
          />

          <VBtn
            variant="text"
            size="small"
            class="stage__remove"
            :disabled="props.disabled || busy"
            @click="askRemove(stage)"
          >
            <template #prepend><IconTrash :size="16" /></template>
            {{ t('tasks.stage.remove') }}
          </VBtn>
        </div>
      </div>
    </div>

    <ConfirmDialog
      v-model="removeOpen"
      :title="t('tasks.stage.remove_title')"
      :text="t('tasks.stage.remove_text')"
      :confirm-label="t('tasks.stage.remove')"
      :loading="busy"
      @confirm="remove"
    />
  </section>
</template>

<style scoped>
.stages {
  display: flex;
  flex-direction: column;
  gap: 6px;
  align-items: flex-start;
}

.stages__header,
.stages__error { align-self: stretch; }

.stage {
  align-self: stretch;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--surface);
}

.stage--open { border-color: var(--border-strong, var(--border)); }

/* The whole header row is clickable: hitting a tiny chevron in a dense list is awkward. */
.stage__head {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  padding: 8px 10px;
  background: none;
  border: 0;
  text-align: left;
  cursor: pointer;
  color: var(--text);
}

.stage__chevron {
  color: var(--text-faint);
  transition: transform 0.15s ease;
}

.stage--open .stage__chevron { transform: rotate(90deg); }

/* Monospaced number: the column of numbers reads top to bottom instead of jumping with digit width. */
.stage__number {
  font-family: var(--font-mono);
  font-size: 12px;
  color: var(--text-faint);
  min-width: 16px;
}

.stage__status { color: var(--text-muted); }

.stage__title {
  flex: 1;
  min-width: 0;
  font-size: 13px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* The evidence mark is a flag, not the text: the pointer itself is long and will not fit the row. */
.stage__evidence-mark {
  font-size: 11px;
  color: var(--success);
  white-space: nowrap;
}

.stage__body {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 4px 10px 12px 32px;
}

.stage__actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.stage__status-select { max-width: 220px; }

.stage__remove { margin-left: auto; color: var(--error); }
</style>
