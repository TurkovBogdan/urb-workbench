<script setup lang="ts">
// Task card: one dialog for create and edit — the fields and checks are shared, the only
// difference is the endpoints called. The mode comes from a prop: `task === null` — create.
//
// The form keeps ITS OWN copy of the values and syncs on open: editing must not change the card
// in the list before saving, and cancel must leave the list untouched.
//
// Status is in the form, but it is sent as a SEPARATE request (`setTaskStatus`): the general
// update does not accept status — only its own endpoint stamps the start, completion and cancel
// timestamps. On create it travels with the card: there is nothing to stamp yet.
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'

import AppDialog from '@/components/AppDialog.vue'
import HelpHint from '@/components/HelpHint.vue'
import LimitField from '@/components/LimitField.vue'
import { errorText } from '@/api/errorText'

import {
  createTask,
  getTask,
  listGroups,
  setTaskStatus,
  updateTask,
  type GroupRow,
  type TaskDetail,
  type TaskListRow,
} from '../api'
import { formatDeadline, parseDay } from '../dates'
import {
  BODY_MAX,
  TASK_CONSTRAINTS_MAX,
  TASK_CONTEXT_MAX,
  TASK_CRITERIA_MAX,
  TASK_DESCRIPTION_MAX,
  TASK_STATUSES,
  TASK_TITLE_MAX,
  TASK_TYPES,
  typeLayout,
} from '../labels'
import TaskPrioritySelect from './TaskPrioritySelect.vue'

const open = defineModel<boolean>({ required: true })

const props = defineProps<{
  /** Workspace the task is created in; the group list depends on it too. */
  workspace: string
  /** Editing an existing task; `null` — creating. */
  task: TaskDetail | TaskListRow | null
  /** Parent of the subtask being created; unused when editing — moving is a separate operation. */
  parent?: TaskListRow | TaskDetail | null
  /**
   * The group is already decided: the task is created from that group's card, `null` — from the
   * "No group" card. The form then does not ask for it. Absent — the person picks.
   */
  group?: string | null
}>()

const emit = defineEmits<{ saved: [code: string] }>()

const { t } = useI18n()

const title = ref('')
const description = ref('')
const context = ref('')
const constraints = ref('')
const criteria = ref('')
const body = ref('')
const type = ref<string>(TASK_TYPES[0])
const status = ref<string>(TASK_STATUSES[0])
const priority = ref<string>('normal')
const groupCode = ref<string | null>(null)
const deadlineAt = ref<Date | null>(null)

const saving = ref(false)
// The task body is still loading: from the list the card arrives WITHOUT it (a list row carries
// no body), and an update is a full replacement of the card. Were the form to save an empty body
// it never loaded, the task text would be erased silently. So the save button is locked while the
// body loads.
const loadingBody = ref(false)
const error = ref<string | null>(null)

const groups = ref<GroupRow[]>([])

const creating = computed(() => props.task === null)

// An empty title is not saved: without it the row is indistinguishable in the list. The backend
// strips whitespace before the length check — so here too a whitespace-only string counts as
// empty.
const valid = computed(() => title.value.trim().length > 0 && !loadingBody.value)

const typeItems = computed(() =>
  TASK_TYPES.map((value) => ({ value, title: t(`tasks.task.type.${value}`) })),
)
const statusItems = computed(() =>
  TASK_STATUSES.map((value) => ({ value, title: t(`tasks.task.status.${value}`) })),
)
const groupItems = computed(() =>
  groups.value.map((group) => ({ value: group.code, title: group.title })),
)

// What the form shows for the selected type. A hidden field keeps going to the backend with its
// previous value: switching the type hides but does not erase — the same rule as on the task page.
const layout = computed(() => typeLayout(type.value))

async function loadGroups() {
  if (!props.workspace) {
    groups.value = []
    return
  }
  try {
    // `report: false` — the lookup loads in the background under the field; the person would not
    // connect a toast about it with what they are doing. An empty group list is more honest: the
    // task will do fine without a group.
    groups.value = await listGroups({ workspace: props.workspace }, { report: false })
  } catch {
    groups.value = []
  }
}

/** Spread the card over the form fields. Texts are taken only from a full task — see `loadingBody`. */
function apply(task: TaskDetail | TaskListRow | null) {
  title.value = task?.title ?? ''
  description.value = task?.description ?? ''
  type.value = task?.type ?? TASK_TYPES[0]
  status.value = task?.status ?? TASK_STATUSES[0]
  priority.value = task?.priority ?? 'normal'
  groupCode.value = task ? task.group_code : (props.group ?? null)
  deadlineAt.value = parseDay(task?.deadline_at ?? null)
  if (task && 'body' in task) applyTexts(task)
}

/** The card's long texts: brief and plan. The form does not show them but must preserve them. */
function applyTexts(task: TaskDetail) {
  context.value = task.context
  constraints.value = task.constraints
  criteria.value = task.criteria
  body.value = task.body
}

watch(() => [open.value, props.task] as const, async ([isOpen, task]) => {
  if (!isOpen) return
  error.value = null
  context.value = ''
  constraints.value = ''
  criteria.value = ''
  body.value = ''
  apply(task)
  void loadGroups()
  // From the list comes a row without the long texts — fetch the full task, otherwise the full
  // card replacement would send an empty brief instead of the written one. Take ONLY the texts
  // from the response: the person may have started editing the other fields meanwhile, and
  // overwriting them would erase what was typed.
  if (!task || 'body' in task) return
  loadingBody.value = true
  try {
    applyTexts(await getTask(task.code, { report: false }))
  } catch (e) {
    error.value = errorText(e)
  } finally {
    loadingBody.value = false
  }
}, { immediate: true })

async function save() {
  if (!valid.value) return
  saving.value = true
  error.value = null
  try {
    // `report: false` — the operation's refusal is shown HERE, next to the button: the dialog stays
    // open with the entered text, while a toast would take the message out of sight.
    if (props.task) {
      let saved = await updateTask(
        props.task.code,
        {
          title: title.value.trim(),
          description: description.value.trim(),
          context: context.value,
          constraints: constraints.value,
          criteria: criteria.value,
          body: body.value,
          type: type.value,
          priority: priority.value,
          group_code: groupCode.value,
          deadline_at: formatDeadline(deadlineAt.value),
        },
        { report: false },
      )
      // A second request, and only on change: status is changed by the endpoint that stamps the
      // phase, and calling it on every save would mark work as started on a typo fix.
      if (status.value !== props.task.status) {
        saved = await setTaskStatus(props.task.code, status.value, { report: false })
      }
      open.value = false
      emit('saved', saved.code)
    } else {
      const saved = await createTask(
        {
          workspace: props.workspace,
          title: title.value.trim(),
          description: description.value.trim(),
          context: context.value,
          constraints: constraints.value,
          criteria: criteria.value,
          body: body.value,
          type: type.value,
          status: status.value,
          priority: priority.value,
          group_code: groupCode.value,
          parent_code: props.parent?.code ?? null,
          deadline_at: formatDeadline(deadlineAt.value),
        },
        { report: false },
      )
      open.value = false
      emit('saved', saved.code)
    }
  } catch (e) {
    error.value = errorText(e)
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <AppDialog
    v-model="open"
    :title="creating ? t('tasks.task.form.create_title') : t('tasks.task.form.title')"
    :description="props.parent && creating ? t('tasks.task.form.under', { title: props.parent.title }) : props.task?.code"
    size="base"
    scrollable
    :persistent="saving"
    :close-disabled="saving"
  >
    <!-- Field order goes from "what is it" to "when": title and description, then the
         classification (type, status, priority, group), then dates, and the long body last. -->
    <div class="task-form">
      <!-- The same limit counter as the task page's editors and the group form: input stops at
           the limit, and the counter warns in advance. -->
      <LimitField
        v-model="title"
        :label="t('tasks.task.form.name')"
        :max-length="TASK_TITLE_MAX"
        variant="outlined"
        hide-details
        autofocus
      />

      <LimitField
        v-model="description"
        :label="t('tasks.task.form.description')"
        :max-length="TASK_DESCRIPTION_MAX"
        multiline
        auto-grow
        variant="outlined"
        rows="2"
        hide-details
      >
        <!-- Inside the field, not in the label: a floating label ignores the pointer, and the
             explanation would never open. -->
        <template #append-inner>
          <HelpHint :text="t('tasks.task.detail.hint.description')" />
        </template>
      </LimitField>

      <!-- Type comes BEFORE the long fields: it decides which of them are shown at all, and
           picking it after the form has expanded to full screen would rearrange fields under the
           cursor. What was written stays on switching — only the display is hidden. -->
      <div class="task-form__field">
        <span class="task-form__label">{{ t('tasks.task.form.type') }}</span>
        <VBtnToggle v-model="type" mandatory density="default" variant="tonal" class="task-form__toggle">
          <VBtn v-for="item in typeItems" :key="item.value" :value="item.value">
            {{ item.title }}
          </VBtn>
        </VBtnToggle>
      </div>

      <div class="task-form__row">
        <VSelect
          v-model="status"
          :items="statusItems"
          :label="t('tasks.task.form.status')"
          :chips="false"
          variant="outlined"
          hide-details
        />
        <TaskPrioritySelect
          v-model="priority"
          :label="t('tasks.task.form.priority')"
          variant="outlined"
          hide-details
        />
      </div>

      <!-- The group is optional: a task without one lands in the "No group" section, not lost. -->
      <VSelect
        v-if="props.group === undefined"
        v-model="groupCode"
        :items="groupItems"
        :label="t('tasks.task.form.group')"
        :placeholder="t('tasks.task.form.no_group')"
        :chips="false"
        variant="outlined"
        clearable
        hide-details
      />

      <!-- The deadline is the only assignable date: the day to finish by. The picked day is sent
           as the last second of that day (`formatDeadline`). -->
      <VDateInput
        v-model="deadlineAt"
        :label="t('tasks.task.form.deadline_at')"
        variant="outlined"
        clearable
      />

      <!-- Until the long texts are loaded the fields are locked: an empty, writable box would look
           like "there is no text", although there is and it is about to arrive. -->
      <VTextarea
        v-model="context"
        :label="t('tasks.task.form.context')"
        :maxlength="TASK_CONTEXT_MAX"
        :disabled="loadingBody"
        :loading="loadingBody"
        variant="outlined"
        rows="4"
        auto-grow
        hide-details
      >
        <template #append-inner>
          <HelpHint :text="t('tasks.task.detail.hint.context')" />
        </template>
      </VTextarea>

      <!-- Constraints, criteria and plan are shown from type `standard` up: a simple task has none,
           and empty fields would stretch the form to full screen without asking anything. -->
      <template v-if="layout.brief">
        <VTextarea
          v-model="constraints"
          :label="t('tasks.task.form.constraints')"
          :maxlength="TASK_CONSTRAINTS_MAX"
          :disabled="loadingBody"
          variant="outlined"
          rows="3"
          auto-grow
          hide-details
        >
          <template #append-inner>
            <HelpHint :text="t('tasks.task.detail.hint.constraints')" />
          </template>
        </VTextarea>

        <VTextarea
          v-model="criteria"
          :label="t('tasks.task.form.criteria')"
          :maxlength="TASK_CRITERIA_MAX"
          :disabled="loadingBody"
          variant="outlined"
          rows="3"
          auto-grow
          hide-details
        >
          <template #append-inner>
            <HelpHint :text="t('tasks.task.detail.hint.criteria')" />
          </template>
        </VTextarea>
      </template>

      <VTextarea
        v-if="layout.plan"
        v-model="body"
        :label="t('tasks.task.form.body')"
        :maxlength="BODY_MAX"
        :disabled="loadingBody"
        :loading="loadingBody"
        variant="outlined"
        rows="5"
        auto-grow
        hide-details
      >
        <template #append-inner>
          <HelpHint :text="t('tasks.task.detail.hint.body')" />
        </template>
      </VTextarea>

      <VAlert v-if="error" type="error" variant="tonal" density="compact">{{ error }}</VAlert>
    </div>

    <template #actions>
      <VBtn variant="text" :disabled="saving" @click="open = false">
        {{ t('common.action.cancel') }}
      </VBtn>
      <VBtn color="primary" variant="flat" :loading="saving" :disabled="!valid" @click="save">
        {{ creating ? t('common.action.add') : t('common.action.save') }}
      </VBtn>
    </template>
  </AppDialog>
</template>

<style scoped>
/* Some fields carry a persistent hint with a counter, so the gap between fields is smaller than
   usual: the hint's own spacing already separates them. */
.task-form {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

/* Two fields in a row: they are about the same thing (task classification, dates) and apart would
   double the dialog's height. Below 520px the row breaks up — on a narrow screen a half-width
   field is unreadable. */
.task-form__row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px;
}

@media (max-width: 520px) {
  .task-form__row { grid-template-columns: 1fr; }
}

/* The label sits closer to its field than the fields sit to each other — otherwise it reads as a
   heading for the whole block rather than the toggle's label. */
.task-form__field {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.task-form__label {
  font-size: 12px;
  color: var(--text-muted);
}

/* A button group's size is not inherited by its children (docs/conventions/frontend.md): 34px plus
   the toggle's 1px outline top and bottom levels it with the neighbouring 36px fields. Set through the
   variable: the global `.v-btn-group .v-btn` rule reads it to beat the group's inline `height: auto`. */
.task-form__toggle { width: 100%; }
.task-form__toggle :deep(.v-btn) { flex: 1; --v-btn-height: 34px; font-size: 0.875rem; }
</style>
