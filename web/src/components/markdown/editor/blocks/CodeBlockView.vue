<script setup lang="ts">
// Node view of an editable code block: the frame of the viewer's `CodeBlock` (header with the
// language, line numbers, copy) around text that stays ProseMirror's. The colour is not drawn here
// — the highlight plugin decorates the content, this view only says which palette is painted.
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { NodeViewContent, NodeViewWrapper, nodeViewProps } from '@tiptap/vue-3'
import { IconCheck, IconCode, IconCopy, IconListNumbers } from '@tabler/icons-vue'
import VSelectSearch from '@/components/VSelectSearch.vue'
import { useSettingsStore } from '@/stores/settings'
import { LANGUAGE_OPTIONS, resolveLanguage, type LanguageOption } from '@/composables/useHighlighter'
import { DIAGRAM_LANGUAGE } from '../../shared/contracts'

const props = defineProps(nodeViewProps)

const { t } = useI18n()
const settings = useSettingsStore()

// The editor's editability is not reactive. Switching it (a task deleted while open) emits
// `update` — without a transaction — so that is the event it is re-read on.
const editable = ref(props.editor.isEditable)
const syncEditable = (): void => { editable.value = props.editor.isEditable }
onMounted(() => props.editor.on('update', syncEditable))
onBeforeUnmount(() => props.editor.off('update', syncEditable))

const language = computed(() => String(props.node.attrs.language ?? ''))
// A fence may name a language by an alias (`py`, `env`) or by something shiki does not know; the
// block keeps it as written, so it is offered as an option of its own at the top of the list.
const languages = computed<LanguageOption[]>(() =>
  !language.value || LANGUAGE_OPTIONS.some((option) => option.value === language.value)
    ? LANGUAGE_OPTIONS
    : [{ value: language.value, name: '', search: language.value }, ...LANGUAGE_OPTIONS],
)
const searchOf = (item: unknown): string => (item as LanguageOption).search
// A fence name shiki does not know is kept as written, and the header says it is drawn as text.
const unknown = computed(() => Boolean(language.value) && language.value !== 'text' && resolveLanguage(language.value) === 'text')

const lineNumbers = ref(settings.typography.codeLineNumbers)
const lineCount = computed(() => Math.max(1, props.node.textContent.split('\n').length))

const copied = ref(false)

// In a field with diagrams a mermaid block is a diagram being edited (diagram.ts): it says so with
// "Done", which turns it back into the picture — as Esc and leaving the block do. Its language is
// fixed: the language is what makes it a diagram, and another one would leave a plain code block
// where the picture was, never to turn back.
const isDiagramSource = computed(() =>
  language.value === DIAGRAM_LANGUAGE && Boolean(props.editor.schema.nodes.diagram))

function finishDiagram(): void {
  const pos = props.getPos()
  if (typeof pos === 'number') props.editor.chain().focus().finishDiagram(pos).run()
}

function setLanguage(value: unknown): void {
  if (isDiagramSource.value) return
  props.updateAttributes({ language: typeof value === 'string' && value !== 'text' ? value : '' })
}

// A refused clipboard (no permission, an insecure origin) leaves the button as it was rather than
// throwing out of a click handler.
async function copy(): Promise<void> {
  try {
    await navigator.clipboard.writeText(props.node.textContent)
  } catch {
    return
  }
  copied.value = true
  setTimeout(() => { copied.value = false }, 1800)
}
</script>

<template>
  <NodeViewWrapper class="code-node" :class="{ 'code-node--numbers': lineNumbers }">
    <div class="code-node__header" contenteditable="false">
      <span class="code-node__lang">
        <IconCode :size="13" stroke-width="2" />
        <span v-if="isDiagramSource" class="code-node__lang-fixed">{{ DIAGRAM_LANGUAGE }}</span>
        <VSelectSearch
          v-else
          :model-value="language || 'text'"
          :items="languages"
          item-title="value"
          item-value="value"
          :item-search="searchOf"
          ranked
          :search-placeholder="t('common.editor.code.search_language')"
          :disabled="!editable"
          variant="plain"
          density="compact"
          hide-details
          :chips="false"
          :menu-props="{ maxHeight: 360, contentClass: 'code-node__menu' }"
          class="code-node__select"
          @update:model-value="setLanguage"
        >
          <template #item="{ props: itemProps, item }">
            <VListItem v-bind="itemProps" density="compact">
              <template #append>
                <span class="code-node__lang-name">{{ (item as LanguageOption).name }}</span>
              </template>
            </VListItem>
          </template>
        </VSelectSearch>
        <span v-if="unknown" class="code-node__unknown">{{ t('common.editor.code.no_highlighting') }}</span>
      </span>
      <div class="code-node__actions">
        <button
          class="code-node__btn"
          :class="{ 'code-node__btn--active': lineNumbers }"
          :title="t('common.code.line_numbers')"
          @click="lineNumbers = !lineNumbers"
        >
          <IconListNumbers :size="14" stroke-width="2" />
        </button>
        <button
          class="code-node__btn"
          :class="{ 'code-node__btn--active': copied }"
          :title="t('common.action.copy')"
          @click="copy"
        >
          <IconCheck v-if="copied" :size="14" stroke-width="2.5" />
          <IconCopy v-else :size="14" stroke-width="2" />
        </button>
        <VBtn
          v-if="isDiagramSource"
          variant="text"
          size="x-small"
          class="code-node__done"
          @click="finishDiagram"
        >
          <template #prepend><IconCheck :size="14" /></template>
          {{ t('common.editor.diagram.done') }}
        </VBtn>
      </div>
    </div>

    <div class="code-node__body">
      <div v-if="lineNumbers" class="code-node__gutter" contenteditable="false" aria-hidden="true">
        <span v-for="line in lineCount" :key="line">{{ line }}</span>
      </div>
      <!-- Identifiers are not words: the browser's spell check underlines half the listing, and
           autocorrect / autocapitalize would rewrite it on mobile keyboards. Prose keeps all three. -->
      <pre class="code-node__pre"><NodeViewContent
        as="code"
        class="code-node__content"
        spellcheck="false"
        autocorrect="off"
        autocapitalize="off"
      /></pre>
    </div>
  </NodeViewWrapper>
</template>

<style scoped>
/* Margins, size and line height follow the viewer's block in a reading body (`.md-code-slot`,
   CodeBlock), so a body does not shift when it switches between reading and editing. */
.code-node {
  margin: 1.5em 0;
  border: 1px solid var(--border-soft);
  border-radius: var(--radius-sm);
  overflow: hidden;
  font-family: var(--font-mono);
}

.code-node__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 2px 10px;
  background: var(--surface);
  border-bottom: 1px solid var(--border-soft);
  user-select: none;
}

.code-node__lang {
  display: flex;
  align-items: center;
  gap: 5px;
  color: var(--text-muted);
  font-size: 11px;
}

.code-node__select {
  flex: 0 0 auto;
  min-width: 110px;
}

/* A diagram's source names its language without offering to change it: the same type and colour
   as the picker's value, and the picker's vertical room, so the header keeps its height. */
.code-node__lang-fixed {
  font-family: var(--font-mono);
  font-size: 11px;
  color: var(--text-muted);
  line-height: 28px;
}

.code-node__select :deep(.v-field__input),
.code-node__select :deep(.v-select__selection-text) {
  font-family: var(--font-mono);
  font-size: 11px;
  color: var(--text-muted);
  min-height: 0;
  padding-top: 4px;
  padding-bottom: 4px;
}

/* In the teleported menu, but rendered from this template's slot, so the scope id reaches it. */
.code-node__lang-name {
  margin-left: 12px;
  font-size: 12px;
  color: var(--text-faint);
}

.code-node__unknown {
  color: var(--text-faint);
  font-style: italic;
}

.code-node__actions {
  display: flex;
  align-items: center;
  gap: 2px;
}

.code-node__btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  border: none;
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--text-faint);
  cursor: pointer;
  transition: background 0.12s, color 0.12s;
}

.code-node__btn:hover {
  background: var(--surface-hi);
  color: var(--text-muted);
}

.code-node__btn--active,
.code-node__btn--active:hover {
  color: var(--accent);
}

.code-node__body {
  display: flex;
  background: var(--surface);
  font-size: var(--reading-code-size, 12px);
  line-height: 1.65;
}

.code-node__gutter {
  display: flex;
  flex-direction: column;
  flex: 0 0 auto;
  padding: 12px 0;
  min-width: 3.4em;
  padding-right: 1.2em;
  text-align: right;
  color: var(--text-faint);
  user-select: none;
}

/* The bare `pre` and `code` rules of main.scss draw a panel and an accent chip; here the frame is
   the wrapper, the pre is only the scroller and the code only the text. */
.code-node .code-node__pre {
  flex: 1 1 auto;
  min-width: 0;
  margin: 0;
  padding: 0;
  border: none;
  border-radius: 0;
  background: none;
  overflow-x: auto;
  font-size: inherit;
  line-height: inherit;
}

.code-node .code-node__pre :deep(code) {
  display: block;
  padding: 12px 14px;
  background: none;
  border: none;
  border-radius: 0;
  font-family: var(--font-mono);
  font-size: inherit;
  /* NodeViewContent writes `white-space: pre-wrap` inline. A wrapped line would desync the gutter
     from the text, so the listing scrolls sideways instead, as it does in CodeBlock. */
  white-space: pre !important;
  tab-size: 2;
  color: var(--text);
}

.code-node--numbers .code-node__pre :deep(code) {
  padding-left: 0;
}

/* The two rules that pick a palette — the same split as in CodeBlock: dark unconditional, light
   as the override keyed by `data-theme`. The class comes from codeHighlight.ts (TOKEN_CLASS). */
.code-node :deep(.code-token) {
  color: var(--shiki-dark);
  font-style: var(--shiki-dark-font-style, inherit);
  font-weight: var(--shiki-dark-font-weight, inherit);
}

html[data-theme='light'] .code-node :deep(.code-token) {
  color: var(--shiki-light);
  font-style: var(--shiki-light-font-style, inherit);
  font-weight: var(--shiki-light-font-weight, inherit);
}

/* Selected code keeps its colours, as in an editor. The app's `::selection` (main.scss) pins the
   ink to `--text` so accent chips stay readable on the wash — and on a listing that turned every
   token black: dragging a block selects it whole on the drop, and the block looked unhighlighted
   until clicked away from. The wash stays; only the ink comes back from the token's palette. */
.code-node :deep(.code-token::selection) {
  color: var(--shiki-dark);
}

html[data-theme='light'] .code-node :deep(.code-token::selection) {
  color: var(--shiki-light);
}
</style>

<style>
/* The menu root is teleported and carries no scope id. Vuetify sizes it to the activator — the
   narrow language field — and ignores a `minWidth` in menu-props, so the floor is set here. */
.code-node__menu {
  min-width: 280px !important;
}
</style>
