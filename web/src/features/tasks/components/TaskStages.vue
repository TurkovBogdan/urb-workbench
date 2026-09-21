<script setup lang="ts">
// Этапы плана: полотно шагов задачи со своим состоянием и доказательством выполнения.
//
// Правится на месте, как и вся деталка: строка разворачивается, поля уезжают по уходу из них.
// Кнопки сохранения нет — её нет и у самой задачи, и второй порядок работы на одной странице
// читался бы как ошибка.
//
// ЗАКРЫТЬ ЭТАП БЕЗ ДОКАЗАТЕЛЬСТВА НЕЛЬЗЯ — это правило бэка, и интерфейс его не дублирует
// проверкой, а показывает: пока `evidence` пуст, кнопка «Готово» заперта и объясняет почему.
// Продублируй мы проверку здесь, у одного правила стало бы два места, и разошлись бы они в первый
// же день.
import { computed, reactive, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { IconChevronRight, IconPlus, IconTrash } from '@tabler/icons-vue'

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
  /** Задача в корзине: править нечего, показываем как есть. */
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

/** Развернуть строку или свернуть её же: второй клик по открытой закрывает. */
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

// ── Набранное, но ещё не отправленное ─────────────────────────────────────────
// Поля уезжают по уходу из них, а у редактора разметки значение приходит событием, не лежит в
// DOM: прочитать его в момент blur, как у `VTextarea`, неоткуда. Поэтому последнее набранное
// копится здесь по паре «этап + поле», а blur его забирает.
type MarkdownField = 'description' | 'body' | 'evidence'

const pending = reactive<Record<string, Partial<Record<MarkdownField, string>>>>({})

function stash(stage: StageRow, field: MarkdownField, value: string): void {
  ;(pending[stage.code] ??= {})[field] = value
}

function flush(stage: StageRow, field: MarkdownField): void {
  const value = pending[stage.code]?.[field]
  delete pending[stage.code]?.[field]
  // Неизменившееся не отправляем: уход из поля, в котором ничего не набрали, не должен
  // выглядеть правкой — ни в журнале изменений, ни по времени обновления задачи.
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
  <div class="stages">
    <VAlert v-if="error" type="error" variant="tonal" density="compact" class="stages__error">
      {{ error }}
    </VAlert>

    <p v-if="!props.stages.length" class="stages__empty">{{ t('tasks.stage.empty') }}</p>

    <div v-for="stage in props.stages" :key="stage.code" class="stage" :class="{ 'stage--open': open === stage.code }">
      <!-- Свёрнутая строка отвечает на три вопроса разом: который по счёту, в каком состоянии и
           о чём. Разворачивают её ради правки и доказательства — то есть редко. -->
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

        <!-- Цель этапа — фраза, поэтому простой режим: заголовку или таблице в ней взяться
             неоткуда, и схема их не знает. -->
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

        <!-- Тело этапа — такой же документ, как план задачи, и потолок у них общий: в бэке это
             одна колонка `BODY_MAX`. -->
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

        <!-- Доказательство — указатель, а не рассказ: подпись под полем говорит, что сюда кладут,
             потому что по имени поля это не угадывается. Отсюда и состав: перечень со строчной
             разметкой, без разделов и таблиц. -->
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

    <VBtn variant="text" size="small" :disabled="props.disabled || busy" @click="add">
      <template #prepend><IconPlus :size="16" /></template>
      {{ t('tasks.stage.add') }}
    </VBtn>

    <ConfirmDialog
      v-model="removeOpen"
      :title="t('tasks.stage.remove_title')"
      :text="t('tasks.stage.remove_text')"
      :confirm-label="t('tasks.stage.remove')"
      :loading="busy"
      @confirm="remove"
    />
  </div>
</template>

<style scoped>
.stages {
  display: flex;
  flex-direction: column;
  gap: 6px;
  align-items: flex-start;
}

.stages__error { align-self: stretch; }

.stages__empty {
  margin: 0;
  font-size: 13px;
  color: var(--text-muted);
}

.stage {
  align-self: stretch;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--surface);
}

.stage--open { border-color: var(--border-strong, var(--border)); }

/* Шапка — вся строка кликабельна: попадать в маленький шеврон при плотном списке неудобно. */
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

/* Номер моноширинным: столбец номеров читается сверху вниз, а не пляшет по ширине цифр. */
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

/* Пометка о доказательстве — не текст, а признак: сам указатель длинный и в строку не поместится. */
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
