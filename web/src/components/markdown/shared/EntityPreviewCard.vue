<script setup lang="ts">
// What an entity code stands for, as the hover card over its pill shows it: the title and the
// description — or why there is nothing to show. One component for both zones, so a pill tells
// the same in the viewer and in the editor.
//
// The code itself is not written out: the pill under the card already shows it. It is copied by
// "Code" in the row of actions.
//
// It only reads the preview store; asking for the code is the body's job (`ensure` once the body is
// drawn), so a card that opens finds the record already there in the usual case. While it is not,
// a skeleton holds the card's place instead of an empty box.
//
// Under a divider, the two ways to go there: open in place, or in a new tab. Only a found entity
// has them — a miss has no page to lead to, and its reason is all the card says.
// "Open" carries the entity's own glyph, the one its pill shows (`shared/document.css`), so the
// button says what it opens; the new tab keeps the interface's usual `external-link`. A file has no
// page in the app to open in place: its "Open" is the tab the browser shows it in, and next to it
// "Download" saves it under the name its holder gave it. Last in the row, for every found entity,
// "Code" copies the code, named by whose it is where the name is short — "Task code", "File code".
import { computed, type Component } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'
import {
  IconAlertCircle,
  IconBook,
  IconCheck,
  IconCopy,
  IconDownload,
  IconExternalLink,
  IconFile,
  IconFileText,
  IconLayoutGrid,
  IconListCheck,
  IconNotebook,
  IconPhoto,
  IconSitemap,
  IconSquareCheck,
} from '@tabler/icons-vue'
import { downloadHref, downloadName, startDownload } from '@/components/files/download'
import { useClipboard } from '@/composables/useClipboard'
import { usePreviews } from '@/stores/preview'
import { refIsFile, type RefType } from './contracts'

const props = defineProps<{ code: string }>()

const TYPE_ICONS: Record<RefType, Component> = {
  TASK: IconSquareCheck,
  TASKGROUP: IconSitemap,
  STAGE: IconListCheck,
  JOURNAL: IconNotebook,
  NOTE: IconFileText,
  WORKSPACE: IconLayoutGrid,
  CODEX: IconBook,
  FILE: IconFile,
  IMAGE: IconPhoto,
}

const ICON = { size: 16, strokeWidth: 1.8 }

const emit = defineEmits<{
  // The card is done: the host closes it.
  opened: []
}>()

const { t, te } = useI18n()
const router = useRouter()
const previews = usePreviews()
const { copy, isCopied } = useClipboard()

const copyLabel = computed(() => (isCopied(props.code) ? t('common.action.copied') : t('common.action.copy_code')))

// "Task code", "Note code"… says whose code it is — where that name is short: the button shares one
// row with two others. A type with a long name (a workspace) or an ambiguous one (`CODEX@` is a
// codex and its entries alike) has no entry in the dictionary and keeps the plain "Code".
const codeLabel = computed(() => {
  const key = `common.editor.ref.preview.code_of.${props.code.split('@')[0].toUpperCase()}`
  return te(key) ? t(key) : t('common.editor.ref.preview.code')
})

const record = computed(() => previews.get(props.code))
const link = computed(() => (record.value && !record.value.error ? record.value.link : ''))
const typeIcon = computed(() => TYPE_ICONS[props.code.split('@')[0] as RefType] ?? IconExternalLink)
// A file has no page in the app to open in place: its one way is the tab the browser shows it in.
const isFile = computed(() => refIsFile(props.code))

function open(): void {
  emit('opened')
  void router.push(link.value)
}

function openInNewTab(): void {
  emit('opened')
  window.open(link.value, '_blank', 'noopener')
}

// Saved under the name the holder gave it, as the media panel saves a picture (`files/download.ts`).
function download(): void {
  emit('opened')
  const name = downloadName(record.value?.title ?? '')
  startDownload(downloadHref(link.value, name), name)
}

const missText = computed(() => {
  const error = record.value?.error
  if (!error) return ''
  const key = `common.editor.ref.preview.${error.code}`
  return te(key) ? t(key) : error.message
})
</script>

<template>
  <div class="ref-preview">
    <template v-if="!record">
      <VSkeletonLoader type="text@2" class="ref-preview__skeleton" />
    </template>
    <template v-else-if="record.error">
      <div class="ref-preview__miss">
        <IconAlertCircle v-bind="ICON" />
        <span>{{ missText }}</span>
      </div>
    </template>
    <template v-else>
      <div class="ref-preview__title">{{ record.title }}</div>
      <div v-if="record.description" class="ref-preview__description">{{ record.description }}</div>
    </template>
    <template v-if="link">
      <VDivider class="ref-preview__divider" />
      <div class="ref-preview__actions">
        <template v-if="isFile">
          <VBtn size="small" variant="text" @click="openInNewTab">
            <template #prepend><IconExternalLink v-bind="ICON" /></template>
            {{ t('common.editor.ref.preview.open') }}
          </VBtn>
          <VBtn size="small" variant="text" @click="download">
            <template #prepend><IconDownload v-bind="ICON" /></template>
            {{ t('common.editor.ref.preview.download') }}
          </VBtn>
        </template>
        <template v-else>
          <VBtn size="small" variant="text" @click="open">
            <template #prepend><component :is="typeIcon" v-bind="ICON" /></template>
            {{ t('common.editor.ref.preview.open') }}
          </VBtn>
          <VBtn size="small" variant="text" @click="openInNewTab">
            <template #prepend><IconExternalLink v-bind="ICON" /></template>
            {{ t('common.editor.ref.preview.open_new_tab') }}
          </VBtn>
        </template>
        <!-- Copying is not a way to leave: the card stays open, and the check shows on the button. -->
        <VBtn size="small" variant="text" :aria-label="`${copyLabel}: ${code}`" @click="copy(code)">
          <template #prepend>
            <IconCheck v-if="isCopied(code)" v-bind="ICON" />
            <IconCopy v-else v-bind="ICON" />
          </template>
          {{ codeLabel }}
        </VBtn>
      </div>
    </template>
  </div>
</template>

<style scoped>
.ref-preview {
  display: flex;
  flex-direction: column;
  gap: 4px;
  width: max-content;
  max-width: 360px;
  min-width: 220px;
  padding: 10px 12px;
}

.ref-preview__title {
  font-size: 0.875rem;
  font-weight: 600;
  line-height: 1.35;
  overflow-wrap: anywhere;
}

.ref-preview__description {
  display: -webkit-box;
  -webkit-line-clamp: 4;
  -webkit-box-orient: vertical;
  overflow: hidden;
  font-size: 0.8125rem;
  line-height: 1.45;
  color: rgba(var(--v-theme-on-surface), var(--v-medium-emphasis-opacity));
  overflow-wrap: anywhere;
}

/* A miss is the whole card: its reason, one line. */
.ref-preview__miss {
  display: flex;
  align-items: center;
  gap: 6px;
  min-height: 20px;
  font-size: 0.8125rem;
  color: rgb(var(--v-theme-error));
}

.ref-preview__skeleton {
  background: transparent;
}

.ref-preview__skeleton :deep(.v-skeleton-loader__text) {
  margin: 4px 0;
}

/* The divider runs the card's full width: the actions are the card's footer, not a line of text. */
.ref-preview__divider {
  margin: 6px -12px 0;
}

.ref-preview__actions {
  display: flex;
  gap: 4px;
  margin: 0 -8px -6px;
}
</style>
