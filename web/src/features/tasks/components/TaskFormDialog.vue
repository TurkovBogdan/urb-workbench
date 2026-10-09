<script setup lang="ts">
// New task: the title, the brief statement and the task's parameters — nothing more. The rest of
// the brief and the agent's work are written on the task page, where each field has its editor;
// an existing task is edited there too, so this dialog only creates.
//
// The dialog is a small task page: the title field as its heading, the brief statement on the left
// as an invisible field, the parameters on the right in the look and measure of the page's right
// column. The person writes the task here once and then meets the same fields in the same places
// there.
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { IconCalendarEvent } from '@tabler/icons-vue'

import AppDialog from '@/components/AppDialog.vue'
import HelpHint from '@/components/HelpHint.vue'
import IconSwatch from '@/components/IconSwatch.vue'
import InvisibleField from '@/components/InvisibleField.vue'
import { MarkdownEditor } from '@/components/markdown/editor'
import SectionHeader from '@/components/SectionHeader.vue'
import VSelectSearch from '@/components/VSelectSearch.vue'
import { errorText } from '@/api/errorText'

import { createTask, listGroups, type GroupRow, type TaskDetail, type TaskListRow } from '../api'
import { formatDeadline } from '../dates'
import { TASK_DESCRIPTION_MAX, TASK_STATUSES, TASK_TITLE_MAX, TASK_TYPES } from '../labels'
import TaskPrioritySelect from './TaskPrioritySelect.vue'
import TaskStatusSelect from './TaskStatusSelect.vue'

const open = defineModel<boolean>({ required: true })

const props = defineProps<{
  /** Workspace the task is created in; the group list depends on it too. */
  workspace: string
  /** Parent of the subtask being created. */
  parent?: TaskListRow | TaskDetail | null
  /**
   * The group is already decided: the task is created from that group's card, `null` — from the
   * "No group" card. The form then does not ask for it. Absent — the person picks.
   */
  group?: string | null
}>()

const emit = defineEmits<{ saved: [code: string, openIt: boolean] }>()

const { t } = useI18n()

const title = ref('')
const description = ref('')
const type = ref<string>(TASK_TYPES[0])
const status = ref<string>(TASK_STATUSES[0])
const priority = ref<string>('normal')
const groupCode = ref<string | null>(null)
const deadlineAt = ref<Date | null>(null)

// Which of the two buttons is saving: only that one spins, both are locked.
const saving = ref<'add' | 'open' | null>(null)
const error = ref<string | null>(null)

const groups = ref<GroupRow[]>([])

// An empty title is not saved: without it the row is indistinguishable in the list. The backend
// strips whitespace before the length check — so here too a whitespace-only string counts as
// empty.
const valid = computed(() => title.value.trim().length > 0)

// A subtask always takes its parent's group — the backend ignores any other — so asking for one
// would only offer a choice that silently does not happen.
const asksGroup = computed(() => props.group === undefined && !props.parent)

const typeItems = computed(() =>
  TASK_TYPES.map((value) => ({ value, title: t(`tasks.task.type.${value}`) })),
)
const groupItems = computed(() =>
  groups.value.map((group) => ({
    value: group.code,
    title: group.title,
    icon: group.icon,
    color: group.color,
  })),
)

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

watch(open, (isOpen) => {
  if (!isOpen) return
  error.value = null
  title.value = ''
  description.value = ''
  type.value = TASK_TYPES[0]
  status.value = TASK_STATUSES[0]
  priority.value = 'normal'
  groupCode.value = props.group ?? null
  deadlineAt.value = null
  void loadGroups()
}, { immediate: true })

async function save(openIt: boolean) {
  if (!valid.value || saving.value) return
  saving.value = openIt ? 'open' : 'add'
  error.value = null
  try {
    // `report: false` — the refusal is shown HERE, next to the buttons: the dialog stays open with
    // the entered text, while a toast would take the message out of sight.
    const saved = await createTask(
      {
        workspace: props.workspace,
        title: title.value.trim(),
        description: description.value.trim(),
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
    emit('saved', saved.code, openIt)
  } catch (e) {
    error.value = errorText(e)
  } finally {
    saving.value = null
  }
}
</script>

<template>
  <AppDialog
    v-model="open"
    :title="t('tasks.task.form.create_title')"
    size="wide"
    :persistent="saving !== null"
    :close-disabled="saving !== null"
  >
    <!-- The title field IS the dialog's heading, as on the task page: the task being written names
         the window, not a generic "New task". A subtask's parent stands above it — where the task
         will live, read before its name. -->
    <template #title>
      <p v-if="props.parent" class="task-form__parent">
        {{ t('tasks.task.form.under', { title: props.parent.title }) }}
      </p>
      <InvisibleField
        v-model="title"
        :placeholder="t('tasks.task.detail.name')"
        :aria-label="t('tasks.task.detail.name')"
        :maxlength="TASK_TITLE_MAX"
        autofocus
        class="task-form__title"
        @keydown.enter.prevent="save(true)"
      />
    </template>

    <div class="task-form">
      <div class="task-form__grid">
        <!-- The brief statement under the same section header as its card on the task page. The
             goal is one or two sentences, hence simple mode, the same as there. -->
        <div class="task-form__texts">
          <SectionHeader
            :title="t('tasks.task.detail.description')"
            :hint="t('tasks.task.detail.hint.description')"
            class="task-form__section"
          />
          <MarkdownEditor
            v-model="description"
            :aria-label="t('tasks.task.detail.description')"
            :max-length="TASK_DESCRIPTION_MAX"
            mode="simple"
            variant="plain"
            min-height="72px"
          />
        </div>

        <!-- The parameters in the order of the task page's right column. -->
        <div class="task-form__params">
          <!-- The group is optional: a task without one lands in the "No group" section, not lost.
               `:chips="false"` is mandatory: with chips Vuetify renders `#chip` and silently ignores
               `#selection`, so the selected group would be left without its icon. -->
          <VSelectSearch
            v-if="asksGroup"
            v-model="groupCode"
            :items="groupItems"
            :label="t('tasks.task.form.group')"
            :search-placeholder="t('tasks.task.detail.group_search')"
            :no-data-text="t('tasks.task.detail.group_empty')"
            :chips="false"
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
              <span class="task-form__group-value">
                <IconSwatch :icon="item.icon ?? ''" :color="item.color ?? ''" :width="20" />
                {{ item.title }}
              </span>
            </template>
          </VSelectSearch>

          <TaskStatusSelect
            v-model="status"
            :label="t('tasks.task.form.status')"
            variant="outlined"
            density="compact"
            hide-details
          />

          <TaskPrioritySelect
            v-model="priority"
            :label="t('tasks.task.form.priority')"
            variant="outlined"
            density="compact"
            hide-details
          />

          <!-- The calendar icon goes INSIDE the field, as on the task page: outside it stands as a
               separate box before the outline and shifts the field off the column's line. -->
          <VDateInput
            v-model="deadlineAt"
            :label="t('tasks.task.form.deadline_at')"
            prepend-icon=""
            :prepend-inner-icon="IconCalendarEvent"
            variant="outlined"
            density="compact"
            clearable
            hide-details
          />

          <div class="task-form__field">
            <span class="task-form__label">
              {{ t('tasks.task.form.type') }}
              <HelpHint :text="t('tasks.task.detail.type_hint')" />
            </span>
            <VBtnToggle
              v-model="type"
              mandatory
              divided
              variant="outlined"
              density="compact"
              class="task-form__toggle"
            >
              <VBtn v-for="item in typeItems" :key="item.value" :value="item.value">
                {{ item.title }}
              </VBtn>
            </VBtnToggle>
          </div>
        </div>
      </div>

      <VAlert v-if="error" type="error" variant="tonal" density="compact">{{ error }}</VAlert>
    </div>

    <template #actions>
      <VBtn variant="text" :disabled="saving !== null" @click="open = false">
        {{ t('common.action.cancel') }}
      </VBtn>
      <VBtn
        variant="tonal"
        :loading="saving === 'add'"
        :disabled="!valid || saving === 'open'"
        @click="save(false)"
      >
        {{ t('common.action.add') }}
      </VBtn>
      <VBtn
        color="primary"
        variant="flat"
        :loading="saving === 'open'"
        :disabled="!valid || saving === 'add'"
        @click="save(true)"
      >
        {{ t('tasks.task.form.add_and_open') }}
      </VBtn>
    </template>
  </AppDialog>
</template>

<style scoped>
/* The grid is decided by the dialog's own width, not the screen's: the dialog is capped at its
   size step, and a narrow screen squeezes it below that. */
.task-form {
  display: flex;
  flex-direction: column;
  gap: 18px;
  container-type: inline-size;
}

/* One column until the parameters fit beside the texts; past 760px — texts 7, parameters 5. The
   threshold keeps the parameter fields no narrower than in the task page's column (~280px): below
   it the type buttons' labels run into their borders. */
.task-form__grid {
  display: grid;
  grid-template-columns: 1fr;
  gap: 24px;
}

@container (min-width: 760px) {
  .task-form__grid { grid-template-columns: 7fr 5fr; }

  /* Side by side the parameters get the rule the task page draws with its column's card edge. */
  .task-form__params {
    padding-left: 24px;
    border-left: 1px solid var(--border-soft);
  }
}

/* No gap of its own: the editor carries its top padding, and with it the header-to-text distance
   comes out the same as in the task page's description card. */
.task-form__texts {
  display: flex;
  flex-direction: column;
  gap: 0;
  min-width: 0;
}

/* `SectionHeader` takes `flex: 1` to fill a row; in this column that would stretch it to the
   height the parameters column sets. */
.task-form__section { flex: none; }

/* Spacing and field sizes copy the task page's right column (`.task-page__settings`): the densest
   field step, and more air between the fields than usual — the floated labels stick out above
   the outline, and a smaller gap glues each label to the field above it. */
.task-form__params {
  display: flex;
  flex-direction: column;
  gap: 18px;
  min-width: 0;
}

/* The parent line reads like the header's description line, only above the title; one line, cut
   with an ellipsis — a long parent title must not push the field down. */
.task-form__parent {
  margin: 0 0 6px;
  overflow: hidden;
  font-size: 13px;
  line-height: 18px;
  color: var(--text-muted);
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* The title is set the way the task page sets its heading (`.task-page__title`). */

.task-form__title :deep(.v-field__input) {
  min-height: 28px;
  padding-block: 4px;
  margin-block: -4px;
  font-size: 22px;
  font-weight: 700;
  line-height: 28px;
}

/* The floated label is set smaller than its value — the same override as on the task page: the
   global `.v-field .v-label` rule pins it to 13px outside the layers, Vuetify's own 0.75em scale
   never reaches it. */
.task-form :deep(.v-field .v-label.v-field-label--floating) {
  font-size: 11px;
  transform: translateY(calc(-50% - 2px));
}

.task-form__field {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.task-form__label {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
  color: var(--text-muted);
}

.task-form__group-value {
  display: inline-flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
}

/* The same buttons as the task page's type toggle: 26px plus the 1px outline top and bottom
   levels them with the 28px fields. The height goes through the variable — the global
   `.v-btn-group .v-btn` rule reads it to beat the group's inline `height: auto`. */
.task-form__toggle { width: 100%; }

.task-form__toggle :deep(.v-btn) {
  flex: 1;
  min-width: 0;
  --v-btn-height: 26px;
  padding-inline: 6px;
  font-size: 12px;
  letter-spacing: 0;
  text-transform: none;
}
</style>
