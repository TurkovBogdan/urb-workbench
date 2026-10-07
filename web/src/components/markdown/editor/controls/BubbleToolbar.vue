<script setup lang="ts">
// A floating toolbar over the selection — instead of a permanent strip at the top. It appears
// where the cursor is working and disappears as soon as the selection is cleared.
//
// Positioning is our own, not @tiptap/extension-bubble-menu: that one takes a ready HTMLElement
// when the editor is created, so the toolbar would have to exist before the component mounts.
// Reversing the initialization order for that costs more than computing the coordinates: with
// ProseMirror they come straight from the view.
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import type { Editor } from '@tiptap/core'
import {
  IconBold, IconItalic, IconStrikethrough, IconCode, IconLink, IconQuote,
  IconClearFormatting, IconList, IconListNumbers, IconListCheck, IconChevronDown,
  IconHash,
} from '@tabler/icons-vue'
import type { Feature, FeatureSet } from '../modes'

const props = defineProps<{ editor: Editor | undefined; tick: number; features: FeatureSet }>()

const { t } = useI18n()

// The toolbar shows what WILL WORK. A button for a disabled feature is not greyed out, it is
// absent: the node or mark is not in the schema, and pressing it would do nothing.
const has = (feature: Feature): boolean => props.features.has(feature)

// The block-type dropdown rests on headings and the quote. With neither of them there is nothing
// to choose from, and the dropdown disappears along with them.
const showBlockMenu = computed(() => has('heading') || has('quote'))
const showMarks = computed(() => has('bold') || has('italic') || has('strike') || has('code'))
// A mode in which the toolbar has nothing to offer must not show an empty card.
const showPanel = computed(() => showBlockMenu.value || showMarks.value
  || has('link') || has('list') || has('entityRef'))

const HEIGHT = 40
const MARGIN = 8

// The toolbar centres on the selection but does not overflow the editor column: the sidebar is
// next to it, and a short selection near the left edge would pull the toolbar onto it. The bounds
// come from the editor's own DOM, and the width is measured — a guessed constant would drift
// away from the set of buttons.
interface Spot { left: number; top: number; bottom: number; min: number; max: number }

const spot = ref<Spot | null>(null)
const panel = ref<HTMLElement | null>(null)
const width = ref(0)
const linkMenu = ref(false)
const linkHref = ref('')
const refMenu = ref(false)
const refCode = ref('')

function place(): void {
  const editor = props.editor
  if (!editor || editor.isDestroyed || !showPanel.value) return hide()

  const { selection } = editor.state
  // The toolbar edits text: without a selection there is nothing to edit. A code block has no
  // inline marks, so there it would only get in the way.
  if (selection.empty || editor.isActive('codeBlock')) return hide()

  const start = editor.view.coordsAtPos(selection.from)
  const end = editor.view.coordsAtPos(selection.to)
  const sameLine = Math.abs(start.top - end.top) < 2
  const bounds = editor.view.dom.getBoundingClientRect()

  spot.value = {
    left: sameLine ? (start.left + end.right) / 2 : start.left,
    top: Math.min(start.top, end.top),
    bottom: Math.max(start.bottom, end.bottom),
    min: Math.max(bounds.left, MARGIN),
    max: Math.min(bounds.right, window.innerWidth - MARGIN),
  }
}

function measure(): void {
  width.value = panel.value?.offsetWidth ?? 0
}

function hide(): void {
  if (linkMenu.value || refMenu.value) return
  spot.value = null
}

// The selection will not survive a focus change, so the buttons must not take focus: mousedown
// is suppressed, the click still arrives, the caret stays where it is.
function hold(event: Event): void {
  event.preventDefault()
}

const style = computed(() => {
  const at = spot.value
  if (!at) return {}
  const half = width.value / 2
  const above = at.top > HEIGHT + MARGIN * 2
  // The centre is clamped so both edges of the toolbar stay inside the editor column.
  const left = Math.min(Math.max(at.left, at.min + half), Math.max(at.min + half, at.max - half))
  return {
    left: `${left}px`,
    ...(above ? { top: `${at.top - HEIGHT - MARGIN}px` } : { top: `${at.bottom + MARGIN}px` }),
  }
})

watch(() => props.tick, place)
watch(() => props.editor, place)
// The button set is fixed, but the dropdowns change their label from "Aa" to "H2" — remeasure.
watch(spot, () => void nextTick(measure))

onMounted(() => {
  measure()
  window.addEventListener('scroll', place, true)
  window.addEventListener('resize', place)
})

onBeforeUnmount(() => {
  window.removeEventListener('scroll', place, true)
  window.removeEventListener('resize', place)
})

// ── State ─────────────────────────────────────────────────────────────────────

function is(name: string, attrs?: Record<string, unknown>): boolean {
  void props.tick
  return props.editor?.isActive(name, attrs) ?? false
}

// The list kind under the cursor. `isActive` will not do here: a checkbox item differs from a
// plain one by its `checked` value, and "any boolean" cannot be expressed as a match in it.
function listKind(): 'bullet' | 'ordered' | 'task' | null {
  void props.tick
  const state = props.editor?.state
  if (!state) return null
  const { $from } = state.selection
  for (let depth = $from.depth; depth > 0; depth -= 1) {
    const node = $from.node(depth)
    if (node.type.name !== 'listItem') continue
    if (node.attrs.checked !== null) return 'task'
    return node.attrs.ordered ? 'ordered' : 'bullet'
  }
  return null
}

// Heading level only: a quote mark as the label read as a stray character, and that the block
// is currently a quote is already visible from the highlighted quote button.
const blockLabel = computed(() => {
  void props.tick
  if (is('heading', { level: 1 })) return 'H1'
  if (is('heading', { level: 2 })) return 'H2'
  if (is('heading', { level: 3 })) return 'H3'
  return 'Aa'
})

const listIcon = computed(() => {
  const kind = listKind()
  if (kind === 'ordered') return IconListNumbers
  if (kind === 'task') return IconListCheck
  return IconList
})

// ── Actions ───────────────────────────────────────────────────────────────────

function chain() {
  return props.editor?.chain().focus()
}

function setBlock(kind: 'paragraph' | 'quote' | 1 | 2 | 3): void {
  if (kind === 'paragraph') chain()?.setParagraph().run()
  else if (kind === 'quote') chain()?.toggleNode('quote', 'paragraph').run()
  else chain()?.toggleHeading({ level: kind }).run()
}

function openLink(): void {
  linkHref.value = String(props.editor?.getAttributes('link').href ?? '')
  linkMenu.value = true
}

function applyLink(): void {
  const href = linkHref.value.trim()
  if (href) chain()?.setLink({ href }).run()
  else chain()?.unsetLink().run()
  linkMenu.value = false
  place()
}

function applyRef(): void {
  const code = refCode.value.trim()
  if (code) chain()?.insertEntityRef(code).run()
  refCode.value = ''
  refMenu.value = false
}
</script>

<template>
  <Teleport to="body">
    <div v-show="spot" ref="panel" class="bubble" :style="style" @mousedown="hold">
      <VCard elevation="8" rounded="lg" class="bubble__card">
        <!-- Block type: same as "Aa ∨" — one dropdown instead of a row of H1/H2/H3 buttons -->
        <VMenu v-if="showBlockMenu" location="bottom start">
          <template #activator="{ props: menu }">
            <button v-bind="menu" class="bubble__btn bubble__btn--wide" :title="t('common.editor.toolbar.block_type')">
              <span class="bubble__label">{{ blockLabel }}</span>
              <IconChevronDown :size="13" />
            </button>
          </template>
          <VList density="compact" nav>
            <VListItem :active="!is('heading') && !is('quote')" @click="setBlock('paragraph')">
              <VListItemTitle>{{ t('common.editor.slash.paragraph') }}</VListItemTitle>
            </VListItem>
            <template v-if="has('heading')">
              <VListItem :active="is('heading', { level: 1 })" @click="setBlock(1)">
                <VListItemTitle>{{ t('common.editor.slash.h1') }}</VListItemTitle>
              </VListItem>
              <VListItem :active="is('heading', { level: 2 })" @click="setBlock(2)">
                <VListItemTitle>{{ t('common.editor.slash.h2') }}</VListItemTitle>
              </VListItem>
              <VListItem :active="is('heading', { level: 3 })" @click="setBlock(3)">
                <VListItemTitle>{{ t('common.editor.slash.h3') }}</VListItemTitle>
              </VListItem>
            </template>
            <VListItem v-if="has('quote')" :active="is('quote')" @click="setBlock('quote')">
              <VListItemTitle>{{ t('common.editor.slash.quote') }}</VListItemTitle>
            </VListItem>
          </VList>
        </VMenu>

        <span v-if="showBlockMenu && showMarks" class="bubble__sep" />

        <button v-if="has('bold')" class="bubble__btn" :class="{ 'is-on': is('bold') }" :title="t('common.editor.toolbar.bold')" @click="chain()?.toggleBold().run()">
          <IconBold :size="16" />
        </button>
        <button v-if="has('italic')" class="bubble__btn" :class="{ 'is-on': is('italic') }" :title="t('common.editor.toolbar.italic')" @click="chain()?.toggleItalic().run()">
          <IconItalic :size="16" />
        </button>
        <button v-if="has('strike')" class="bubble__btn" :class="{ 'is-on': is('strike') }" :title="t('common.editor.toolbar.strike')" @click="chain()?.toggleStrike().run()">
          <IconStrikethrough :size="16" />
        </button>
        <button v-if="has('code')" class="bubble__btn" :class="{ 'is-on': is('code') }" :title="t('common.editor.toolbar.code')" @click="chain()?.toggleCode().run()">
          <IconCode :size="16" />
        </button>

        <VMenu v-if="has('link')" v-model="linkMenu" location="bottom" :close-on-content-click="false">
          <template #activator="{ props: menu }">
            <button v-bind="menu" class="bubble__btn" :class="{ 'is-on': is('link') }" :title="t('common.editor.toolbar.link')" @click="openLink">
              <IconLink :size="16" />
            </button>
          </template>
          <VCard class="pa-2" width="300">
            <VTextField
              v-model="linkHref"
              autofocus
              density="compact"
              variant="outlined"
              placeholder="https://…"
              hide-details
              @keydown.enter.prevent="applyLink"
            />
            <div class="d-flex justify-end mt-2 ga-2">
              <VBtn size="small" variant="text" @click="linkHref = ''; applyLink()">{{ t('common.editor.toolbar.unlink') }}</VBtn>
              <VBtn size="small" color="primary" @click="applyLink">{{ t('common.editor.toolbar.apply') }}</VBtn>
            </div>
          </VCard>
        </VMenu>

        <button v-if="has('quote')" class="bubble__btn" :class="{ 'is-on': is('quote') }" :title="t('common.editor.slash.quote')" @click="setBlock('quote')">
          <IconQuote :size="16" />
        </button>
        <button v-if="showMarks" class="bubble__btn" :title="t('common.editor.toolbar.clear_formatting')" @click="chain()?.unsetAllMarks().run()">
          <IconClearFormatting :size="16" />
        </button>

        <!-- Lists: also one dropdown, like "☰ ∨" in the reference design -->
        <VMenu v-if="has('list')" location="bottom">
          <template #activator="{ props: menu }">
            <button v-bind="menu" class="bubble__btn bubble__btn--wide" :class="{ 'is-on': !!listKind() }" :title="t('common.editor.toolbar.list')">
              <component :is="listIcon" :size="16" />
              <IconChevronDown :size="13" />
            </button>
          </template>
          <VList density="compact" nav>
            <VListItem :active="listKind() === 'bullet'" @click="chain()?.toggleFlatList({ ordered: false, checked: null }).run()">
              <VListItemTitle>{{ t('common.editor.toolbar.bullet') }}</VListItemTitle>
            </VListItem>
            <VListItem :active="listKind() === 'ordered'" @click="chain()?.toggleFlatList({ ordered: true, checked: null }).run()">
              <VListItemTitle>{{ t('common.editor.toolbar.ordered') }}</VListItemTitle>
            </VListItem>
            <VListItem :active="listKind() === 'task'" @click="chain()?.toggleFlatList({ ordered: false, checked: false }).run()">
              <VListItemTitle>{{ t('common.editor.slash.taskList') }}</VListItemTitle>
            </VListItem>
          </VList>
        </VMenu>

        <span v-if="has('entityRef')" class="bubble__sep" />

        <VMenu v-if="has('entityRef')" v-model="refMenu" location="bottom end" :close-on-content-click="false">
          <template #activator="{ props: menu }">
            <button v-bind="menu" class="bubble__btn" :title="t('common.editor.toolbar.entity_ref')">
              <IconHash :size="16" />
            </button>
          </template>
          <VCard class="pa-2" width="320">
            <VTextField
              v-model="refCode"
              autofocus
              density="compact"
              variant="outlined"
              placeholder="AREA@0123456789"
              hide-details
              style="font-family: var(--font-mono)"
              @keydown.enter.prevent="applyRef"
            />
            <div class="d-flex justify-end mt-2">
              <VBtn size="small" color="primary" @click="applyRef">{{ t('common.editor.toolbar.insert') }}</VBtn>
            </div>
          </VCard>
        </VMenu>
      </VCard>
    </div>
  </Teleport>
</template>

<style scoped>
.bubble {
  position: fixed;
  z-index: 2500;
  transform: translateX(-50%);
}

.bubble__card {
  display: flex;
  align-items: center;
  gap: 1px;
  padding: 3px 5px;
  height: 40px;
}

.bubble__btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 2px;
  min-width: 28px;
  height: 28px;
  padding: 0 5px;
  border: none;
  border-radius: 6px;
  background: none;
  color: var(--text-muted);
  cursor: pointer;
  transition: background 0.12s ease, color 0.12s ease;
}

.bubble__btn--wide {
  padding: 0 4px 0 7px;
}

.bubble__btn:hover {
  background: color-mix(in srgb, rgb(var(--v-theme-on-surface)) 9%, transparent);
  color: var(--text);
}

.bubble__btn.is-on {
  color: rgb(var(--v-theme-primary));
}

.bubble__label {
  font-size: 13px;
  line-height: 1;
}

.bubble__sep {
  width: 1px;
  height: 18px;
  margin: 0 4px;
  background: var(--border-soft);
}
</style>
