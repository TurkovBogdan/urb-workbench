<script setup lang="ts">
import { computed } from 'vue'

import HelpHint from './HelpHint.vue'

// Section header — the in-page sibling of PageHeader: a title and optional description on the
// left, an optional slot on the right (counter, button, badge). `level` sets BOTH the semantic tag
// (h1…h6) AND the font size, so nested sections give a proper document structure rather than a
// set of identical lines.
//
// The "back" button does NOT go here: it belongs to the page, not a section within it, and lives
// in PageHeader — which is built on top of this same component (level 1) so that the heading
// anatomy is one for both levels.
const props = withDefaults(defineProps<{
  title?: string
  description?: string
  level?: 1 | 2 | 3 | 4 | 5 | 6
  /** A number next to the title: how many items the section holds in total. */
  count?: number
  /** An explanation behind a "?" right after the title — for what is read once, not every time. */
  hint?: string
  /** Data is still loading — placeholders of their size stand in for the title and description. */
  loading?: boolean
}>(), {
  title: '',
  description: undefined,
  level: 2,
  count: undefined,
  hint: undefined,
  loading: false,
})

const tag = computed(() => `h${props.level}` as const)
</script>

<template>
  <div class="section-header" :class="`section-header--l${level}`">
    <div class="section-header__text">
      <template v-if="loading">
        <VSkeletonLoader type="heading" class="section-header__skel section-header__skel--title" />
        <VSkeletonLoader type="text" class="section-header__skel section-header__skel--desc" />
      </template>

      <template v-else>
        <!-- `title` is a slot for when the title isn't text but a component of its own. The WHOLE
             element is replaced, tag included: such a component needs full control of its metrics,
             otherwise <h*> would impose its own font size and margins. -->
        <slot name="title">
          <component :is="tag" class="section-header__title">
            {{ title }}
            <span v-if="count !== undefined" class="section-header__count">{{ count }}</span>
            <HelpHint v-if="hint" :text="hint" />
          </component>
        </slot>
        <p v-if="description || $slots.description" class="section-header__desc">
          <slot name="description">{{ description }}</slot>
        </p>
      </template>
    </div>

    <div v-if="$slots.right" class="section-header__right">
      <slot name="right" />
    </div>
  </div>
</template>

<style scoped>
.section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  flex: 1;
  min-width: 0;
}

.section-header__text {
  min-width: 0;
}

.section-header__title {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 0;
  color: var(--text);
  font-weight: 600;
  letter-spacing: -0.02em;
  line-height: 1.3;
}

/* Spacing for a section within a page. Level one doesn't get it: there the page header owns the
   distance to the content, and a second value in the same place would drift from the first. */
.section-header:not(.section-header--l1) {
  margin: 4px 0 10px;
}

/* Font size is a function of level: semantics and weight are set by a single knob. */
.section-header--l1 .section-header__title { font-size: 18px; }
.section-header--l2 .section-header__title { font-size: 14px; }
.section-header--l3 .section-header__title { font-size: 13px; }
.section-header--l4 .section-header__title,
.section-header--l5 .section-header__title,
.section-header--l6 .section-header__title { font-size: 12px; }

.section-header__count {
  font-size: 12px;
  font-weight: 500;
  color: var(--text-faint);
}

.section-header__desc {
  margin: 3px 0 0;
  max-width: 640px;
  color: var(--text-muted);
  font-size: 13px;
  line-height: 1.5;
}

.section-header__right {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  gap: 8px;
}

/* Placeholders repeat the title and description metrics. Vuetify sets the bone width inline
   (100% of the loader), so the root is constrained and only the bone's height and margin are touched. */
.section-header__skel { padding: 0; background: transparent; }
.section-header__skel--title { width: 280px; max-width: 55%; }
.section-header__skel--desc  { width: 180px; max-width: 38%; }
.section-header__skel--title :deep(.v-skeleton-loader__bone) { height: 16px; margin: 3px 0; }
.section-header__skel--desc  :deep(.v-skeleton-loader__bone) { height: 10px; margin: 8px 0 0; }

/* On the narrowest screens the right part wraps below the text. */
@media (max-width: 599px) {
  .section-header {
    flex-wrap: wrap;
    align-items: flex-start;
  }
  .section-header__right {
    width: 100%;
  }
}
</style>
