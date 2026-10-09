<script setup lang="ts">
// Detail page navigation: the first panel of the sticky rail.
//
// It takes the place a header takes on lists, and stays on screen along the whole document — so
// it is reachable from any reading position, not only from the top of the page.
//
// It has one job — to leave; actions on the object live next to its name in the content. But the
// panel also takes what the page uses along the whole reading length (search in the document):
// such tools sit UNDER the exit in the same card, not in a separate frame below — two panels in a
// row read as two different blocks, though they share one job, the rail.
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { IconCheck, IconChevronLeft, IconCopy, IconSettings } from '@tabler/icons-vue'

import { useClipboard } from '@/composables/useClipboard'
import { useNavigationHistory } from '@/composables/useNavigationHistory'

import DocumentAppearance from './DocumentAppearance.vue'

const props = withDefaults(defineProps<{
  /** Where to go when there is no history: the nearest parent in the tree. */
  parent: string
  /** Name of the fallback place — "To the research list". Shown on the button only when that is
      where leaving will go: on entry via a direct link. Without it, always "Back". */
  label?: string
  /** Code of the shown object. While it is absent (the page is loading), there is no copy button. */
  code?: string
  /** The page shows a document: a gear for its appearance appears in the exit row. */
  appearance?: boolean
}>(), {
  label: '',
  code: '',
  appearance: false,
})

const { t } = useI18n()
const router = useRouter()
const { goBack, hasHistory } = useNavigationHistory()
const { copy, isCopied } = useClipboard()

// The label names what the button will do. With history it returns "where you came from" — that
// is "Back", and it can't promise the research list: you may well have come from a zone. The
// place name stays with the fallback address, used when entering via a direct link.
const backLabel = computed(() =>
  hasHistory.value ? t('common.action.back') : props.label || t('common.action.back'),
)

// One exit per page: we leave to where we came from. There is no list of places further up the
// tree — the way up is walked by the same presses, each removing one level. A direct entry leaves
// no history, and then "back" means "one level up".
function back(): void {
  goBack(router, props.parent)
}

// The appearance fields are closed by default and expand in the rail, not in a dialog: they are
// tweaked while looking at the text beside them, and a dialog would cover exactly what they are
// touched for.
const appearanceOpen = ref(false)
</script>

<template>
  <VCard variant="outlined" rounded="lg" class="detail-nav">
    <div class="detail-nav__row">
      <!-- A chevron on its own tile: a single stroke with no shaft — at 28px an arrow with a tail
           reads like a technical drawing, and it says "left" without one. Tile and label are one
           element, not a button next to text: they do one job, and two tab stops would not make
           it any clearer. -->
      <button type="button" class="detail-nav__back" @click="back">
        <span class="detail-nav__glyph"><IconChevronLeft :size="18" :stroke-width="1.6" /></span>
        {{ backLabel }}
      </button>

      <!-- An unlabelled gear: it is not about this page but about HOW to show it, and a label
           would put it on par with the exit. The button itself holds the open state. -->
      <VBtn
        v-if="appearance"
        icon
        variant="text"
        class="detail-nav__gear"
        :active="appearanceOpen"
        :title="t('settings.interface.group.document.title')"
        @click="appearanceOpen = !appearanceOpen"
      >
        <IconSettings :size="18" :stroke-width="1.6" />
      </VBtn>
    </div>

    <!-- The rule separates the exit from the reading tools: one leads off the page, the other
         works inside it. Its ends run into the padding — it divides the card rather than sitting
         in it. -->
    <template v-if="$slots.default || code">
      <VDivider class="detail-nav__rule" />
      <slot />

      <!-- The object's code at hand along the whole reading length: the same button exists in
           the content header too, but the header scrolls away with the first screen while the
           rail stays. It sits among the reading tools, under search, at full width — here it has a
           label, since the icon alone doesn't say WHAT gets copied. -->
      <VBtn v-if="code" block variant="tonal" @click="copy(code)">
        <template #prepend>
          <IconCheck v-if="isCopied(code)" :size="16" class="detail-nav__copied" />
          <IconCopy v-else :size="16" />
        </template>
        {{ t('common.action.copy_code') }}
      </VBtn>
    </template>
  </VCard>

  <!-- The appearance fields are a separate card UNDER the panel, not inside it: they appear and
       go away, and inside the shared frame that would look like the navigation growing. -->
  <VExpandTransition>
    <DocumentAppearance v-if="appearance && appearanceOpen" />
  </VExpandTransition>
</template>

<style scoped>
.detail-nav {
  padding: 12px;
  margin-bottom: 12px;
  display: flex;
  flex-direction: column;
  gap: 10px;
  min-width: 0;
  flex: none;
}

.detail-nav__rule {
  margin: 0 -12px;
}

/* The exit takes the row, the gear is pushed to its right edge: it is not a second exit but a
   display setting, and sits where the page actions sit in the content header. */
.detail-nav__row {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.detail-nav__row .detail-nav__back {
  flex: 1;
}

/* The box is set here, not via props: for an icon button Vuetify computes the side as
   `--v-btn-height + 12px`, and density only changes the height (see
   docs/frontend/vuetify-css-patterns). The side is the same 28px as the exit tile opposite. */
.detail-nav__gear {
  width: 28px;
  min-width: 28px;
  height: 28px;
  flex: none;
  color: var(--text-faint);
}

.detail-nav__gear:hover {
  color: var(--text);
}

/* The same grey as the copy checkmark in the content header: success is signalled by the icon
   change, not its colour. */
.detail-nav__copied {
  color: var(--text-muted);
}

/* Button style reset: the browser draws a grey bordered box, while a "glyph + text" row is needed. */
.detail-nav__back {
  appearance: none;
  border: 0;
  background: transparent;
  padding: 0;
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
  font-family: var(--font);
  font-size: 13px;
  font-weight: 500;
  line-height: 1.35;
  text-align: left;
  color: var(--text-muted);
  cursor: pointer;
  transition: color 0.14s ease;
}

.detail-nav__back:hover {
  color: var(--text);
}

/* The same glyph tile as the back button in `PageHeader` (`variant="tonal"` = own colour at 8%),
   only 28px instead of 32: in the rail it stands next to text, not alone before a page title. */
.detail-nav__glyph {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  flex: none;
  border-radius: var(--radius-sm);
  background: color-mix(in oklab, currentColor 8%, transparent);
  transition: background-color 0.14s ease;
}
</style>
