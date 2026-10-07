<script setup lang="ts">
// Section navigation for a long page: a sticky column of links highlighting the section currently
// being read.
//
// What scrolls is not the window but the content zone (`PageLayout` → `.page-layout__content`), so
// that is what to listen to and scroll: `window.scrollY` is always zero here, and `scrollIntoView`
// would drag the whole layout along with the zone.
import {
  computed,
  onActivated,
  onBeforeUnmount,
  onMounted,
  ref,
  type ComponentPublicInstance,
} from 'vue'

export interface NavSection {
  /** The `id` of the section element on the page. */
  id: string
  label: string
  /** Shown next to the label, like the counter on a section heading. */
  count?: number
  /** Nesting: 0 (default) — a page section, 1 — a heading inside it. */
  depth?: number
}

const props = defineProps<{ sections: NavSection[] }>()

// The list is a `TransitionGroup`, so the ref points at a component, while its root node is what's needed.
const root = ref<ComponentPublicInstance | null>(null)
const listElement = computed(() => (root.value?.$el ?? null) as HTMLElement | null)
const activeId = ref('')

// Breathing room above a section scrolled to: without it the heading hits the very edge and
// reads as cut off.
const SCROLL_OFFSET = 48

// A section becomes current once its top rises above this line — not from the very edge,
// otherwise the highlight jumps on the first pixel of scrolling. The line is below where a
// scroll-to lands, so a section that has arrived is highlighted right away.
const ACTIVE_LINE_OFFSET = SCROLL_OFFSET + 48

// Margin from the bottom within which the page counts as scrolled to the end. The last section is
// often shorter than the screen and by the line rule would never activate.
const BOTTOM_EPSILON = 4

const scroller = computed(
  () => listElement.value?.closest('.page-layout__content') as HTMLElement | null,
)

function sectionElement(id: string): HTMLElement | null {
  return scroller.value?.querySelector(`#${CSS.escape(id)}`) ?? null
}

function syncActive() {
  const container = scroller.value
  if (!container || !props.sections.length) return

  const reachedBottom =
    container.scrollTop + container.clientHeight >= container.scrollHeight - BOTTOM_EPSILON
  if (reachedBottom) {
    activeId.value = props.sections[props.sections.length - 1].id
    return
  }

  const line = container.getBoundingClientRect().top + ACTIVE_LINE_OFFSET
  let current = props.sections[0].id
  for (const section of props.sections) {
    const element = sectionElement(section.id)
    if (element && element.getBoundingClientRect().top <= line) current = section.id
  }
  activeId.value = current
}

function goTo(id: string) {
  const container = scroller.value
  const element = sectionElement(id)
  if (!container || !element) return
  const offset = element.getBoundingClientRect().top - container.getBoundingClientRect().top
  container.scrollTo({
    top: Math.max(0, container.scrollTop + offset - SCROLL_OFFSET),
    behavior: 'smooth',
  })
}

function listen() {
  scroller.value?.addEventListener('scroll', syncActive, { passive: true })
  window.addEventListener('resize', syncActive)
}

function unlisten() {
  scroller.value?.removeEventListener('scroll', syncActive)
  window.removeEventListener('resize', syncActive)
}

onMounted(() => {
  listen()
  syncActive()
})

// KeepAlive keeps the page alive between visits: the listener was never removed, but the scroll
// position is restored only after activation — recompute.
onActivated(syncActive)
onBeforeUnmount(unlisten)
</script>

<template>
  <VCard variant="outlined" rounded="lg" tag="nav" class="section-nav">
    <!-- The item list changes in two cases: under search (sections leave and come back) and on moving
         to another artifact — the column lives in the shared frame and survives it. In both the
         change is shown with motion: an instant swap reads as the page being swapped under your hand. -->
    <TransitionGroup ref="root" tag="div" name="nav-item" class="section-nav__list">
      <button
        v-for="section in sections"
        :key="section.id"
        type="button"
        class="section-nav__link"
        :class="{
          'section-nav__link--active': section.id === activeId,
          'section-nav__link--nested': section.depth,
        }"
        @click="goTo(section.id)"
      >
        <span class="section-nav__label">{{ section.label }}</span>
        <span v-if="section.count !== undefined" class="section-nav__count">{{ section.count }}</span>
      </button>
    </TransitionGroup>
  </VCard>
</template>

<style scoped>
/* A plate of the same kind as the section cards (outlined + rounded lg come as props), so the
   table of contents reads as one more page block rather than a set of bare links. */
/* The page sets height and stickiness (the component doesn't know what sits next to it in the
   column); here is only the inner structure: the list takes the remainder and scrolls by itself
   if a long document's table of contents is taller than the space given. */
.section-nav {
  padding: 6px;
  display: flex;
  min-height: 0;
}

.section-nav__list {
  display: flex;
  flex-direction: column;
  gap: 1px;
  min-height: 0;
  flex: 1;
  overflow-y: auto;
}

/* Collapsing items relies on `interpolate-size` (auto ↔ 0); where it is unsupported the list
   changes instantly, as before. */
.section-nav__list {
  interpolate-size: allow-keywords;
}

/* The motion here is functional: whoever it bothers has turned it off in the system settings. */
@media (prefers-reduced-motion: reduce) {
  .nav-item-enter-active,
  .nav-item-leave-active,
  .nav-item-move {
    transition: none;
  }
}

/* Button style reset: the element is chosen for its behaviour (not navigation but scrolling its
   own page), yet it must look like a link — without the reset the browser draws a grey plate with a border. */
.section-nav__link {
  appearance: none;
  border: 0;
  font: inherit;
  position: relative;
  display: flex;
  align-items: center;
  gap: 8px;
  /* Wider on the left: the current-section marker lives there and its space is always reserved —
     otherwise the label would twitch sideways when highlighted. */
  padding: 7px 10px 7px 20px;
  border-radius: var(--radius-sm);
  background: transparent;
  font-size: 13px;
  line-height: 1.45;
  text-align: start;
  color: var(--text-muted);
  cursor: pointer;
  transition: color 0.14s ease, background-color 0.14s ease;
}

/* The marker is a separate rounded bar INSIDE the item, not its border: a border would be clipped by
   the corner rounding and read as a defect. It also grows from a dot into a stroke when the section
   changes, so the move between items shows as motion rather than a blink. */
.section-nav__link::before {
  content: '';
  position: absolute;
  left: 9px;
  top: 50%;
  width: 2px;
  height: 3px;
  border-radius: 1px;
  background: var(--text-faint);
  transform: translateY(-50%);
  opacity: 0;
  transition: height 0.18s ease, opacity 0.14s ease, background-color 0.14s ease;
}

.section-nav__link:hover {
  color: var(--text);
  background: var(--surface-hi);
}

.section-nav__link:hover::before {
  opacity: 1;
}

.section-nav__link--active {
  color: var(--text);
  background: var(--accent-soft);
  font-weight: 500;
}

.section-nav__link--active::before {
  height: 15px;
  opacity: 1;
  background: var(--accent);
}

/* A nested item is a heading inside a section: indented under the parent's marker and set smaller
   so the list reads as a tree, not a solid strip. Long headings are truncated to one line: in a
   narrow column wrapping onto three lines eats the whole table of contents. */
.section-nav__link--nested {
  padding-left: 32px;
  font-size: 12px;
  color: var(--text-faint);
}

.section-nav__link--nested .section-nav__label {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.section-nav__link--nested::before {
  left: 21px;
}

.section-nav__link--nested:hover {
  color: var(--text-muted);
}

.section-nav__link--nested.section-nav__link--active {
  color: var(--text);
}

.section-nav__label {
  min-width: 0;
  flex: 1;
}

.section-nav__count {
  font-family: var(--font-mono);
  font-size: 11px;
  color: var(--text-faint);
  transition: color 0.14s ease;
}

.section-nav__link--active .section-nav__count {
  color: var(--text-muted);
}

/* Narrow screen: there is no separate column for the panel any more — it lies above the content as
   a row of links. Stickiness is harmful there: a pinned strip would eat the already scarce height. */
@media (max-width: 1099px) {
  .section-nav__list {
    flex-direction: row;
    flex-wrap: wrap;
    gap: 4px;
  }

  /* In a row the stroke marker isn't needed: items sit side by side and the fill shows the current one. */
  .section-nav__link {
    padding-inline: 12px;
  }

  .section-nav__link::before {
    display: none;
  }
}

/* Items entering and leaving. An item doesn't just fade but collapses in height — otherwise the plate
   would jump over neatly melting rows. These rules come AFTER `.section-nav__link`: they have equal
   specificity, and the item's own `transition` would otherwise override this one.
   `min-height: 0` is required: a column-flex item's default minimum height equals its content, so
   it wouldn't shrink to zero — the collapse would stall at one line of text. */
.nav-item-enter-active,
.nav-item-leave-active {
  overflow: hidden;
  min-height: 0;
  transition:
    opacity 0.18s ease,
    transform 0.18s ease,
    height 0.18s ease,
    padding-top 0.18s ease,
    padding-bottom 0.18s ease;
}

.nav-item-move {
  transition: transform 0.18s ease;
}

.nav-item-enter-from,
.nav-item-leave-to {
  opacity: 0;
  height: 0;
  padding-top: 0;
  padding-bottom: 0;
  transform: translateY(-4px);
}

/* The motion here is functional: whoever it bothers has turned it off in the system settings. */
@media (prefers-reduced-motion: reduce) {
  .nav-item-enter-active,
  .nav-item-leave-active,
  .nav-item-move {
    transition: none;
  }
}
</style>
