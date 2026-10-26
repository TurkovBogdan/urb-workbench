<script setup lang="ts">
// The panel under a picture shown full screen — the one every media picture gets. On the left, what
// the picture is called and what is in it; on the right, download, open in a tab, copy its code.
//
// A stored picture (`code`) is read from its preview, so a title saved here, in another tab or by
// the agent shows as soon as the change feed brings it. The title and the description are edited
// right where they are read when the page's own entity holds the file (`held`) and the page lends
// its editor (`FILE_BINDING_EDITOR`): a field saves when it is left, the title on Enter too (the
// description takes Enter as a new line, Ctrl+Enter saves it); Esc puts back what was there and
// does not close the viewer. Anywhere else they are only read. A picture that is not stored (a
// message's image) has no code to copy and nothing to edit — the panel keeps its two links.
//
// The panel is as wide as what it says, up to `--media-panel-max-width`, and when that changes — the
// next picture, a word typed — its width flows to the new one rather than jumping. A width of
// `auto` cannot be animated, so the content is measured as it is laid out (`ResizeObserver`) and
// the box is given that width in pixels, with a transition. The edited fields grow with their text
// the same way a reading line does: each sits over an invisible copy of its text that sizes it.
//
// Clicks stay inside: the stage under the panel closes the viewer.
import { computed, inject, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { IconCheck, IconCopy, IconDownload, IconExternalLink } from '@tabler/icons-vue'

import { errorText } from '@/api/errorText'
import { useClipboard } from '@/composables/useClipboard'
import { usePreviews } from '@/stores/preview'

import { downloadHref as downloadHrefOf, downloadName as downloadNameOf } from './download'
import { FILE_BINDING_EDITOR } from './fileBinding'

const props = defineProps<{
  src: string
  /** `IMAGE@…` — a stored picture; unset — any other image. */
  code?: string
  /** What the caller knows of the picture, when it has no preview to read. */
  title?: string
  description?: string
}>()

const { t } = useI18n()
const previews = usePreviews()
const editor = inject(FILE_BINDING_EDITOR, null)
const { copy, isCopied } = useClipboard()

const record = computed(() => (props.code ? previews.get(props.code) : undefined))
const shownTitle = computed(() => record.value?.title ?? props.title ?? '')
const shownDescription = computed(() => record.value?.description ?? props.description ?? '')
const editable = computed(() => Boolean(props.code && record.value?.held && editor && !editor.readonly()))

// ── Editing ───────────────────────────────────────────────────────────────────
type Field = 'title' | 'description'

const draft = ref<Record<Field, string>>({ title: '', description: '' })
const focused = ref<Field | null>(null)
const failure = ref('')

// A field being typed in keeps its text; the other follows what the preview says.
watch([shownTitle, shownDescription], ([title, description]) => {
  if (focused.value !== 'title') draft.value.title = title
  if (focused.value !== 'description') draft.value.description = description
}, { immediate: true })

watch(() => props.code, () => { failure.value = '' })

const shown = (field: Field): string => (field === 'title' ? shownTitle.value : shownDescription.value)

async function commit(field: Field): Promise<void> {
  focused.value = null
  const value = draft.value[field].trim()
  if (!editor || !props.code || value === shown(field)) {
    draft.value[field] = shown(field)
    return
  }
  failure.value = ''
  try {
    await editor.save(`FILE@${props.code.split('@')[1]}`, { [field]: value })
  } catch (error) {
    failure.value = t('common.media_panel.save_failed', { reason: errorText(error) })
    draft.value[field] = shown(field)
  }
}

function revert(field: Field, event: KeyboardEvent): void {
  draft.value[field] = shown(field)
  ;(event.target as HTMLElement).blur()
}

function leave(event: KeyboardEvent): void {
  (event.target as HTMLElement).blur()
}

// ── Actions ───────────────────────────────────────────────────────────────────
const downloadName = computed(() => downloadNameOf(shownTitle.value))

// A stored picture is saved through the storage's download address, under its name; any other image
// is left to the browser's own download of its address.
const downloadHref = computed(() => (props.code ? downloadHrefOf(props.src, downloadName.value) : props.src))

const copied = computed(() => Boolean(props.code && isCopied(props.code)))

// ── Width ─────────────────────────────────────────────────────────────────────
// `null` until the first measure: the panel opens at its width, the transition is for changes.
const content = ref<HTMLElement | null>(null)
const width = ref<number | null>(null)
const settled = ref(false)
let observer: ResizeObserver | null = null

onMounted(() => {
  if (!content.value) return
  observer = new ResizeObserver(([entry]) => {
    const next = Math.ceil(entry.borderBoxSize?.[0]?.inlineSize ?? entry.target.getBoundingClientRect().width)
    if (width.value !== null) settled.value = true
    width.value = next
  })
  observer.observe(content.value)
})

onBeforeUnmount(() => observer?.disconnect())
</script>

<template>
  <div
    class="media-panel"
    :class="{ 'media-panel--settled': settled }"
    :style="width === null ? undefined : { width: `${width}px` }"
    @click.stop
  >
    <div ref="content" class="media-panel__content">
      <div class="media-panel__text">
        <template v-if="editable">
          <!-- Each field over an invisible copy of its text: the copy gives the width and the
               height, the field fills them. A trailing blank keeps room for the caret. -->
          <div class="media-panel__grow media-panel__grow--title">
            <span class="media-panel__mirror" aria-hidden="true">{{ (draft.title || t('common.media_panel.title')) + ' ' }}</span>
            <input
              v-model="draft.title"
              class="media-panel__field"
              :placeholder="t('common.media_panel.title')"
              :aria-label="t('common.media_panel.title')"
              maxlength="256"
              size="1"
              @focus="focused = 'title'"
              @blur="commit('title')"
              @keydown.enter.prevent="leave"
              @keydown.esc.stop.prevent="revert('title', $event)"
            >
          </div>
          <div class="media-panel__grow media-panel__grow--description">
            <span class="media-panel__mirror" aria-hidden="true">{{ (draft.description || t('common.media_panel.description')) + ' ' }}</span>
            <textarea
              v-model="draft.description"
              class="media-panel__field"
              :placeholder="t('common.media_panel.description')"
              :aria-label="t('common.media_panel.description')"
              maxlength="256"
              rows="1"
              @focus="focused = 'description'"
              @blur="commit('description')"
              @keydown.ctrl.enter.prevent="leave"
              @keydown.meta.enter.prevent="leave"
              @keydown.esc.stop.prevent="revert('description', $event)"
            />
          </div>
        </template>
        <template v-else>
          <div v-if="shownTitle" class="media-panel__title">{{ shownTitle }}</div>
          <div v-if="shownDescription" class="media-panel__description">{{ shownDescription }}</div>
        </template>
        <div v-if="failure" class="media-panel__failure" role="alert">{{ failure }}</div>
      </div>

      <div class="media-panel__actions">
        <a
          class="media-panel__action"
          :href="downloadHref"
          :download="downloadName"
          :title="t('common.media_panel.download')"
          :aria-label="t('common.media_panel.download')"
        >
          <IconDownload :size="18" :stroke-width="1.8" />
        </a>
        <a
          class="media-panel__action"
          :href="src"
          target="_blank"
          rel="noopener"
          :title="t('common.media_panel.open')"
          :aria-label="t('common.media_panel.open')"
        >
          <IconExternalLink :size="18" :stroke-width="1.8" />
        </a>
        <button
          v-if="code"
          type="button"
          class="media-panel__action"
          :title="copied ? t('common.action.copied') : t('common.action.copy_code')"
          :aria-label="copied ? t('common.action.copied') : t('common.action.copy_code')"
          @click="copy(code)"
        >
          <IconCheck v-if="copied" :size="18" :stroke-width="2" />
          <IconCopy v-else :size="18" :stroke-width="1.8" />
        </button>
      </div>
    </div>
  </div>
</template>

<style scoped>
/* A thin bar in the viewer's light-on-dark: the text takes the room, the actions keep theirs. */
/* The box: the panel's look, and the width it is given in pixels — a transition once it has one.
   Before the first measure it simply fits its content. What overflows mid-change is clipped. */
.media-panel {
  box-sizing: content-box;
  width: max-content;
  max-width: 100%;
  overflow: hidden;
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 8px;
  background: rgba(24, 27, 34, 0.86);
  color: #fff;
  cursor: auto;
  text-align: left;
}

.media-panel--settled {
  transition: width 0.24s cubic-bezier(0.2, 0.8, 0.2, 1);
}

/* What the panel says, as wide as it needs up to the limit its place sets: this is what is measured. */
.media-panel__content {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  box-sizing: border-box;
  width: max-content;
  max-width: var(--media-panel-max-width, 640px);
  padding: 8px 8px 8px 12px;
}

.media-panel__text {
  display: flex;
  flex: 0 1 auto;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
  padding-top: 3px;
}

.media-panel__title,
.media-panel__grow--title {
  font-size: 14px;
  font-weight: 600;
  line-height: 1.4;
  color: #fff;
}

.media-panel__description,
.media-panel__grow--description {
  font-size: 13px;
  line-height: 1.5;
  color: rgba(255, 255, 255, 0.72);
}

/* A title reads in two lines at most. A description is shown whole, read or edited: it grows the
   panel down as far as it goes, to ten lines — more than 256 characters fill — and only past them
   scrolls. Where the panel stands makes room for it. */
.media-panel__title {
  display: -webkit-box;
  -webkit-line-clamp: 2;
  line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.media-panel__description {
  max-height: calc(13px * 1.5 * 10);
  overflow-y: auto;
  white-space: pre-line;
  overflow-wrap: anywhere;
}

/* A field and the invisible copy of its text share one cell: the copy sizes it. Pulled out by the
   field's own padding, so its text stands where the read text does. */
.media-panel__grow {
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  margin: 0 -4px;
}

.media-panel__grow > * {
  grid-area: 1 / 1;
  min-width: 0;
  padding: 1px 4px;
}

.media-panel__mirror {
  visibility: hidden;
  overflow: hidden;
}

.media-panel__grow--title .media-panel__mirror { white-space: pre; }

.media-panel__grow--description .media-panel__mirror {
  max-height: calc(13px * 1.5 * 10 + 2px);
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}

/* An edited field reads as the text it holds; under the pointer and in focus a faint plate says it
   takes typing. */
.media-panel__field {
  display: block;
  width: 100%;
  height: 100%;
  box-sizing: border-box;
  border: 0;
  border-radius: 4px;
  outline: none;
  background: transparent;
  color: inherit;
  font: inherit;
  resize: none;
  overflow-y: auto;
  transition: background 0.12s ease;
}

.media-panel__field:hover { background: rgba(255, 255, 255, 0.06); }
.media-panel__field:focus { background: rgba(255, 255, 255, 0.1); }
.media-panel__field::placeholder { color: rgba(255, 255, 255, 0.4); font-weight: 400; }

.media-panel__failure {
  font-size: 12px;
  line-height: 1.4;
  color: #ff8a8c;
}

.media-panel__actions {
  display: flex;
  flex: none;
  gap: 2px;
}

.media-panel__action {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 30px;
  height: 30px;
  padding: 0;
  border: 0;
  border-radius: 6px;
  background: transparent;
  color: rgba(255, 255, 255, 0.72);
  cursor: pointer;
  text-decoration: none;
  transition: background 0.12s ease, color 0.12s ease;
}

.media-panel__action:hover,
.media-panel__action:focus-visible {
  background: rgba(255, 255, 255, 0.12);
  color: #fff;
  outline: none;
}
</style>
