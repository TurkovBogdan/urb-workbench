<script setup lang="ts">
// Where an archive comes in: dropped from the computer onto the zone, or chosen by a click.
//
// The zone registers with the window's guard (`useFileDropZone`): without it the guard would answer
// «no» over the dialog, and a file dropped beside the zone would open in the browser. One file of
// the expected extension is the only thing it takes; anything else is refused right here, before a
// byte goes anywhere — the server would say the same, only after the whole upload.
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { IconFileImport, IconUpload } from '@tabler/icons-vue'

import { useFileDropZone } from '@/composables/useFileDrop'

const props = defineProps<{
  /** With the dot: `.utsk`, `.ucdx`. */
  extension: string
  /** What the archive is, for the lead line: «файл задачи .utsk». */
  lead: string
  disabled?: boolean
}>()

const emit = defineEmits<{ file: [file: File] }>()

const { t } = useI18n()

const root = ref<HTMLElement | null>(null)
const input = ref<HTMLInputElement | null>(null)
const refusal = ref('')

const zone = useFileDropZone(root, () => !props.disabled)

function take(files: FileList | null | undefined): void {
  if (!files || files.length === 0) return
  if (files.length > 1) {
    refusal.value = t('common.transfer.drop.one_file')
    return
  }
  const file = files[0]
  if (!file.name.toLowerCase().endsWith(props.extension)) {
    refusal.value = t('common.transfer.drop.wrong_extension', { ext: props.extension })
    return
  }
  refusal.value = ''
  emit('file', file)
}

function onDrop(event: DragEvent): void {
  if (props.disabled) return
  take(event.dataTransfer?.files)
}

function choose(): void {
  if (!props.disabled) input.value?.click()
}

function onPicked(event: Event): void {
  const target = event.target as HTMLInputElement
  take(target.files)
  // The same file chosen again gives no `change` while the old value stays in the field.
  target.value = ''
}
</script>

<template>
  <div
    ref="root"
    class="transfer-drop"
    :class="{
      'transfer-drop--armed': zone.armed.value,
      'transfer-drop--over': zone.over.value,
      'transfer-drop--disabled': disabled,
    }"
    role="button"
    tabindex="0"
    :aria-disabled="disabled"
    @click="choose"
    @keydown.enter.prevent="choose"
    @keydown.space.prevent="choose"
    @drop.prevent="onDrop"
  >
    <IconFileImport :size="40" :stroke-width="1.2" class="transfer-drop__icon" />
    <p class="transfer-drop__lead">{{ t('common.transfer.drop.lead', { what: lead }) }}</p>
    <p class="transfer-drop__hint">{{ t('common.transfer.drop.hint') }}</p>
    <VBtn variant="tonal" color="primary" size="small" :prepend-icon="IconUpload" :disabled="disabled" @click.stop="choose">
      {{ t('common.transfer.drop.choose') }}
    </VBtn>

    <!-- The refusal stands in the zone itself: it is about what was dropped here. -->
    <VAlert v-if="refusal" type="error" variant="tonal" density="compact" class="transfer-drop__refusal" @click.stop>
      {{ refusal }}
    </VAlert>

    <input ref="input" type="file" :accept="extension" class="transfer-drop__input" @change="onPicked">
  </div>
</template>

<style scoped>
/* A dashed line invites a drop: the card's solid frame is around already, and a second solid one
   would read as a nested block rather than a target. */
.transfer-drop {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  padding: 36px 24px;
  border: 2px dashed var(--border);
  border-radius: var(--radius);
  text-align: center;
  cursor: pointer;
  outline: none;
  transition: border-color 0.12s ease, background 0.12s ease;
}

.transfer-drop:focus-visible {
  border-color: rgb(var(--v-theme-primary));
}

.transfer-drop--armed {
  border-color: var(--accent);
}

.transfer-drop--over {
  border-style: solid;
  border-color: rgb(var(--v-theme-primary));
  background: var(--accent-soft);
}

.transfer-drop--disabled {
  cursor: default;
  opacity: 0.6;
}

.transfer-drop__icon {
  color: var(--text-faint);
}

.transfer-drop__lead {
  margin: 0;
  font-size: 15px;
  font-weight: 600;
  color: var(--text);
}

.transfer-drop__hint {
  margin: 0 0 4px;
  max-width: 420px;
  font-size: 13px;
  color: var(--text-muted);
}

.transfer-drop__refusal {
  max-width: 420px;
  margin-top: 4px;
  text-align: left;
  cursor: default;
}

.transfer-drop__input {
  display: none;
}
</style>
