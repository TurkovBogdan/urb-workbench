<script setup lang="ts">
// The workspace card: title, description, icon and colour. One dialog for create and edit — they
// share fields and checks, and differ in exactly two places (the title and the endpoint called);
// a second component for those would mean two forms drifting apart at the very first new column.
// The mode is set by a prop: `workspace === null` — create.
//
// The dialog anatomy (header, body, button bar) comes from AppDialog, only the fields are here. The
// form keeps ITS OWN copy of the values and syncs on open: an edit must not change the card in the
// list before saving, and a cancel must leave the list untouched.
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'

import AppDialog from '@/components/AppDialog.vue'
import IconColorPicker from '@/components/IconColorPicker.vue'
import LimitField from '@/components/LimitField.vue'
import { errorText } from '@/api/errorText'

import { colorNames, colorVarsByName } from '@/shared/colors'
import { iconByName, iconNames } from '@/shared/icons'
import { createWorkspace, updateWorkspace, type WorkspaceBody, type WorkspaceRow } from '../api'

// The limits mirror the DB columns (`workspace/constants.py`: TITLE_MAX / DESCRIPTION_MAX). The
// backend won't accept anything longer (422), but finding that out after submitting means losing
// what was typed: the field itself prevents overtyping. The description is one line under the
// name — the same 128 as a task group's.
const TITLE_MAX = 96
const DESCRIPTION_MAX = 128
/** Default position mirrors `constants.py::SORT_DEFAULT` — the middle of the scale. */
const SORT_DEFAULT = 500

const open = defineModel<boolean>({ required: true })

const props = defineProps<{ workspace: WorkspaceRow | null }>()
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

const creating = computed(() => props.workspace === null)

// An empty title is not saved: without a name the card is indistinguishable in the list. The
// backend trims whitespace before the length check — so here too a whitespace-only string counts
// as empty. A description stored before the limit existed may still be longer than it: the field
// shows it in red rather than cutting it, and the save waits until the person shortens it.
const valid = computed(() =>
  title.value.trim().length > 0 && description.value.trim().length <= DESCRIPTION_MAX,
)

watch(() => [open.value, props.workspace] as const, ([isOpen, workspace]) => {
  if (!isOpen) return
  title.value = workspace?.title ?? ''
  description.value = workspace?.description ?? ''
  icon.value = workspace?.icon || null
  color.value = workspace?.color || null
  sort.value = workspace?.sort ?? SORT_DEFAULT
  error.value = null
}, { immediate: true })

async function save() {
  if (!valid.value) return
  saving.value = true
  error.value = null
  const body: WorkspaceBody = {
    title: title.value.trim(),
    description: description.value.trim(),
    color: color.value ?? '',
    icon: icon.value ?? '',
    sort: Number(sort.value) || SORT_DEFAULT,
  }
  try {
    // `report: false` — the operation failure is shown HERE, next to the button: the dialog stays
    // open with the typed text, and a toast would take the message out of sight.
    await (props.workspace
      ? updateWorkspace(props.workspace.code, body, { report: false })
      : createWorkspace(body, { report: false }))
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
    :title="creating ? t('workspace.form.create_title') : t('workspace.form.title')"
    :description="props.workspace?.code"
    size="base"
    :persistent="saving"
    :close-disabled="saving"
  >
    <!-- Order: what it is (title, description) → how it looks (icon and colour). The picker goes
         last — it is the tallest, and nothing above it should jump while scrolling. -->
    <div class="workspace-form">
      <VTextField
        v-model="title"
        :label="t('workspace.form.name')"
        :maxlength="TITLE_MAX"
        variant="outlined"
        hide-details
        autofocus
      />

      <LimitField
        v-model="description"
        :label="t('workspace.form.description')"
        :max-length="DESCRIPTION_MAX"
        multiline
        auto-grow
        variant="outlined"
        rows="1"
        hide-details
      />

      <!-- As in the group form: a number, not drag and drop — there are only a handful of
           workspaces. Higher `sort` comes first. -->
      <VNumberInput
        v-model="sort"
        :label="t('workspace.form.sort')"
        :hint="t('workspace.form.sort_hint')"
        persistent-hint
        :min="0"
        :step="10"
        control-variant="stacked"
        variant="outlined"
      />

      <div class="workspace-form__field">
        <span class="workspace-form__label">{{ t('workspace.form.look') }}</span>
        <!-- The badge preview lives inside the panel, next to the palette: glyph and colour are
             judged together, there is nothing to choose them by separately.
             The name sets are shared frontend registries (`shared/colors.ts` / `shared/icons.ts`),
             the same as for research groups: one palette per app, there must be no second copy. -->
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
/* The group form's rhythm: the fields are hide-details — the description's counter sits inside
   the field — so nothing below them adds air, and at a smaller gap a floating label nearly
   touches the field above. */
.workspace-form {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

/* The label sits closer to its field than the fields do to each other — otherwise it reads as the
   heading of the whole block rather than the picker's label. */
.workspace-form__field {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin-top: 4px;
}

.workspace-form__label {
  font-size: 12px;
  color: var(--text-muted);
}
</style>
