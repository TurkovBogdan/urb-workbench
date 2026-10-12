<script setup lang="ts">
// Segment, title and "when to read it" — the three lines a codex and a codex note are found by. One
// dialog for creating a codex, editing one, and adding a note under a parent: the fields and their
// checks are the same, only the call differs. The text itself (a codex's rules, a note's body) is
// written in the editor, not here. A codex also has a look — icon and colour, as a workspace and a
// task group; a note has none.
//
// Laid out as the new-task dialog (`TaskFormDialog`): the title field is the window's heading, the
// description on the left under the header it has on the material page, the code and the look on
// the right in a column of parameters.
import { computed, nextTick, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'

import AppDialog from '@/components/AppDialog.vue'
import CopyChip from '@/components/CopyChip.vue'
import IconColorPicker from '@/components/IconColorPicker.vue'
import InvisibleField from '@/components/InvisibleField.vue'
import { MarkdownEditor } from '@/components/markdown/editor'
import SectionHeader from '@/components/SectionHeader.vue'
import { errorText } from '@/api/errorText'
import { colorNames, colorVarsByName } from '@/shared/colors'
import { iconByName, iconNames } from '@/shared/icons'

import {
  createCodex,
  createNote,
  getCodex,
  updateCodex,
  type CodexDetail,
  type CodexNote,
  type CodexRow,
} from '../api'
import { CODEX_DESCRIPTION_MAX, CODEX_SEGMENT_MAX, CODEX_SEGMENT_PATTERN, CODEX_TITLE_MAX } from '../labels'
import { segmentFromTitle } from '../segment'
import { keepSegmentChars } from '@/shared/utils/validators'

const open = defineModel<boolean>({ required: true })

const props = defineProps<{
  /** Edit this codex; `null` with no `parentCode` — create a codex. */
  codex?: CodexRow | null
  /** Create a note under this codex or note. */
  parentCode?: string | null
  parentPath?: string
}>()

const emit = defineEmits<{ saved: [row: CodexDetail | CodexNote] }>()

const { t } = useI18n()

const segment = ref('')
const title = ref('')
const description = ref('')
const icon = ref<string | null>(null)
const color = ref<string | null>(null)
const saving = ref(false)

const icons = iconNames()
const colors = colorNames()
const error = ref<string | null>(null)

const forNote = computed(() => Boolean(props.parentCode))
const heading = computed(() => {
  if (forNote.value) return t('codex.form.note_title')
  return props.codex ? t('codex.form.edit_title') : t('codex.form.create_title')
})

const segmentValid = computed(() => CODEX_SEGMENT_PATTERN.test(segment.value.trim()))
const valid = computed(() => segmentValid.value && title.value.trim().length > 0)

// While the segment is the one suggested from the title, it follows the title; once the person
// types their own, it is theirs.
const segmentTouched = ref(false)

watch(open, (isOpen) => {
  if (!isOpen) return
  segment.value = props.codex?.segment ?? ''
  title.value = props.codex?.title ?? ''
  description.value = props.codex?.description ?? ''
  icon.value = props.codex?.icon || null
  color.value = props.codex?.color || null
  segmentTouched.value = Boolean(props.codex)
  error.value = null
}, { immediate: true })

watch(title, (value) => {
  if (!segmentTouched.value) segment.value = segmentFromTitle(value)
})

// Only what a segment may hold gets in. The raw value lands first and the filtered one a tick
// later: when filtering returns the old value, the model would not change and the field would keep
// showing the refused character.
async function onSegmentInput(value: string) {
  segmentTouched.value = true
  segment.value = value
  await nextTick()
  segment.value = keepSegmentChars(value)
}

async function save() {
  if (!valid.value) return
  saving.value = true
  error.value = null
  const fields = { segment: segment.value.trim(), title: title.value.trim(), description: description.value.trim() }
  const look = { color: color.value ?? '', icon: icon.value ?? '' }
  try {
    let saved: CodexDetail | CodexNote
    if (forNote.value) {
      saved = await createNote({ ...fields, body: '', parent_code: props.parentCode! }, { report: false })
    } else if (props.codex) {
      // The rules are not on this form, and a list row does not carry them: they are read fresh
      // and sent back untouched — the update is whole, and an empty body would wipe them.
      const current = await getCodex(props.codex.code, { report: false })
      saved = await updateCodex(props.codex.code, { ...fields, ...look, body: current.body }, { report: false })
    } else {
      saved = await createCodex({ ...fields, ...look, body: '' }, { report: false })
    }
    open.value = false
    emit('saved', saved)
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
    :title="heading"
    size="wide"
    :persistent="saving"
    :close-disabled="saving"
  >
    <!-- The title field IS the dialog's heading, as in the new-task dialog: the record being written
         names the window. Above it, where the record stands — the parent's path for a note; for a
         codex being edited, its code, copied with a click as in the task page's header. Enter in
         the title saves. -->
    <template #title>
      <p v-if="forNote && parentPath" class="codex-form__context">{{ parentPath }}</p>
      <div v-else-if="codex" class="codex-form__code">
        <CopyChip :text="codex.code" :hint="t('common.action.copy_code')" />
      </div>
      <InvisibleField
        v-model="title"
        :placeholder="t('codex.form.name')"
        :aria-label="t('codex.form.name')"
        :maxlength="CODEX_TITLE_MAX"
        autofocus
        class="codex-form__title"
        @keydown.enter.prevent="save"
      />
    </template>

    <div class="codex-form">
      <div class="codex-form__grid">
        <!-- The description under the same header as on the material page; its "?" is no Tab stop:
             the title and the description are written in one go. -->
        <div class="codex-form__texts">
          <SectionHeader
            :title="t('codex.form.description')"
            :hint="t('codex.form.description_hint')"
            :hint-tabbable="false"
            class="codex-form__section"
          />
          <MarkdownEditor
            v-model="description"
            :aria-label="t('codex.form.description')"
            :max-length="CODEX_DESCRIPTION_MAX"
            mode="simple"
            variant="plain"
            min-height="72px"
          />
        </div>

        <div class="codex-form__params">
          <VTextField
            :model-value="segment"
            :label="t('codex.form.segment')"
            :maxlength="CODEX_SEGMENT_MAX"
            :error="segment.length > 0 && !segmentValid"
            hide-details
            variant="outlined"
            density="compact"
            @update:model-value="onSegmentInput"
            @keydown.enter.prevent="save"
          />
          <div v-if="!forNote" class="codex-form__field">
            <span class="codex-form__label">{{ t('codex.form.look') }}</span>
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
        </div>
      </div>

      <VAlert v-if="error" type="error" variant="tonal" density="compact">{{ error }}</VAlert>
    </div>

    <template #actions>
      <VBtn variant="text" :disabled="saving" @click="open = false">
        {{ t('common.action.cancel') }}
      </VBtn>
      <VBtn color="primary" variant="flat" :loading="saving" :disabled="!valid" @click="save">
        {{ codex ? t('common.action.save') : t('common.action.add') }}
      </VBtn>
    </template>
  </AppDialog>
</template>

<style scoped>
/* The new-task dialog's measures (`TaskFormDialog.vue` explains each): one column until the
   parameters fit beside the description, then two equal halves with the parameters' rule on the
   left — the icon picker needs the room a task's selects do not. */
.codex-form {
  display: flex;
  flex-direction: column;
  gap: 18px;
  container-type: inline-size;
}

.codex-form__grid {
  display: grid;
  grid-template-columns: 1fr;
  gap: 24px;
}

@container (min-width: 760px) {
  .codex-form__grid { grid-template-columns: 1fr 1fr; }

  .codex-form__params {
    padding-left: 24px;
    border-left: 1px solid var(--border-soft);
  }
}

.codex-form__texts {
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.codex-form__section { flex: none; }

.codex-form__params {
  display: flex;
  flex-direction: column;
  gap: 18px;
  min-width: 0;
}

/* The context line reads like the header's description line, only above the title. */
.codex-form__context {
  margin: 0 0 6px;
  overflow: hidden;
  font-size: 13px;
  line-height: 18px;
  color: var(--text-muted);
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* The chip carries its own padding for the hover fill; pulled back so its text stands on the
   title's left edge. */
.codex-form__code {
  margin: 0 0 4px -5px;
}

/* The title is set as the task dialog's and the task page's heading. */
.codex-form__title :deep(.v-field__input) {
  min-height: 28px;
  padding-block: 4px;
  margin-block: -4px;
  font-size: 22px;
  font-weight: 700;
  line-height: 28px;
}

/* The floated label smaller than its value — the task dialog's override of the global 13px rule. */
.codex-form :deep(.v-field .v-label.v-field-label--floating) {
  font-size: 11px;
  transform: translateY(calc(-50% - 2px));
}

/* The task group form's rhythm: the label sits closer to its picker than the fields to each other. */
.codex-form__field {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin-top: 4px;
}

.codex-form__label {
  font-size: 12px;
  color: var(--text-muted);
}
</style>
