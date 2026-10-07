<script setup lang="ts">
// Group card: name, description, appearance and position in the list. One dialog for create and
// edit — as with workspaces: the fields are shared, the only difference is the title and the
// endpoint called.
//
// The workspace is not picked in the form: a group is created in the CURRENT one (its code comes
// as a prop), and editing does not accept it at all — moving a group would drag all its tasks
// along.
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'

import AppDialog from '@/components/AppDialog.vue'
import IconColorPicker from '@/components/IconColorPicker.vue'
import LimitField from '@/components/LimitField.vue'
import { errorText } from '@/api/errorText'

import { colorNames, colorVarsByName } from '@/shared/colors'
import { iconByName, iconNames } from '@/shared/icons'
import { createGroup, updateGroup, type GroupBody, type GroupRow } from '../api'
import { GROUP_DESCRIPTION_MAX, TASK_TITLE_MAX } from '../labels'

/** Default position mirrors `constants.py::SORT_DEFAULT` — the middle of the scale. */
const SORT_DEFAULT = 500

const open = defineModel<boolean>({ required: true })

const props = defineProps<{
  /** Workspace the group is created in. Unused when editing. */
  workspace: string
  /** Editing an existing group; `null` — creating. */
  group: GroupRow | null
}>()

const emit = defineEmits<{ saved: [] }>()

const { t } = useI18n()

const icons = iconNames()
const colors = colorNames()

const title = ref('')
const description = ref('')
const icon = ref<string | null>(null)
const color = ref<string | null>(null)
const sort = ref<number>(SORT_DEFAULT)
const saving = ref(false)
const error = ref<string | null>(null)

const creating = computed(() => props.group === null)

// An empty name is not saved: without a name the group is indistinguishable in the list. The
// backend strips whitespace before the length check — so here too a whitespace-only string counts
// as empty. A description stored before the limit existed may still be longer than it: the field
// shows it in red rather than cutting it, and the save waits until the person shortens it.
const valid = computed(() =>
  title.value.trim().length > 0 && description.value.trim().length <= GROUP_DESCRIPTION_MAX,
)

watch(() => [open.value, props.group] as const, ([isOpen, group]) => {
  if (!isOpen) return
  title.value = group?.title ?? ''
  description.value = group?.description ?? ''
  icon.value = group?.icon || null
  color.value = group?.color || null
  sort.value = group?.sort ?? SORT_DEFAULT
  error.value = null
}, { immediate: true })

async function save() {
  if (!valid.value) return
  saving.value = true
  error.value = null
  const body: GroupBody = {
    title: title.value.trim(),
    description: description.value.trim(),
    color: color.value ?? '',
    icon: icon.value ?? '',
    sort: Number(sort.value) || SORT_DEFAULT,
  }
  try {
    // `report: false` — the refusal is shown HERE, next to the button: the dialog stays open with
    // the entered text, while a toast would take the message out of sight.
    await (props.group
      ? updateGroup(props.group.code, body, { report: false })
      : createGroup(props.workspace, body, { report: false }))
    open.value = false
    emit('saved')
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
    :title="creating ? t('tasks.group.form.create_title') : t('tasks.group.form.title')"
    :description="props.group?.code"
    size="base"
    :persistent="saving"
    :close-disabled="saving"
  >
    <div class="group-form">
      <VTextField
        v-model="title"
        :label="t('tasks.group.form.name')"
        :maxlength="TASK_TITLE_MAX"
        variant="outlined"
        hide-details
        autofocus
      />

      <LimitField
        v-model="description"
        :label="t('tasks.group.form.description')"
        :max-length="GROUP_DESCRIPTION_MAX"
        multiline
        auto-grow
        variant="outlined"
        rows="1"
        hide-details
      />

      <!-- Position is a number, not drag and drop: a workspace has only a handful of groups, and a
           sortable list just for their order is premature. Higher `sort` comes first. -->
      <VNumberInput
        v-model="sort"
        :label="t('tasks.group.form.sort')"
        :hint="t('tasks.group.form.sort_hint')"
        persistent-hint
        :min="0"
        :step="10"
        control-variant="stacked"
        variant="outlined"
      />

      <div class="group-form__field">
        <span class="group-form__label">{{ t('tasks.group.form.look') }}</span>
        <IconColorPicker
          v-model:icon="icon"
          v-model:color="color"
          :icons="icons"
          :colors="colors"
          :resolve-icon="iconByName"
          :resolve-color="colorVarsByName"
          :height="160"
          clearable
        />
      </div>

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
/* Wider than the task form on purpose: its fields carry hints and counters that add air below each
   one, these are hide-details, and at 10px the floating label of one field nearly touched the
   field above. The workspace form shares this rhythm. */
.group-form {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

/* The label sits closer to its field than the fields sit to each other — otherwise it reads as a
   heading for the whole block rather than the picker's label. */
.group-form__field {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin-top: 4px;
}

.group-form__label {
  font-size: 12px;
  color: var(--text-muted);
}
</style>
