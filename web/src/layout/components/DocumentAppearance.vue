<script setup lang="ts">
// Document appearance at hand right next to the document: the same groups as "Document
// appearance", "Code block appearance" and "Diagrams" on `/settings/interface`, complete, in the
// same order and with the same controls — the sets must not diverge, otherwise one and the same
// setting lives in two places under different group names. Where options are ordered (typefaces,
// sizes, weight, width), the control is `VSelectStepper`: people step through neighbours one by
// one comparing the result, and that matters more here than on the settings page — the comparison
// is against live text right beside it.
//
// They are picked by eye against live text, not against a sample on the settings page: size, line
// length and typefaces are good or bad on THIS particular body. The setting is still one and the
// same (`useSettingsStore`, the source of truth is the database via `synced`, localStorage below it
// only a cache until the first frame), so a choice made here shows there too. The labels are
// shared as well: the settings dictionary is their only home.
//
// Unlike the settings page there are no descriptions under the fields: in a 320px rail they would
// take more room than the fields themselves, and explaining the choice is the settings page's job.
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

import SwitchPanel from '@/components/SwitchPanel.vue'
import VSelectStepper from '@/components/VSelectStepper.vue'
import { useAppearanceOptions, type DescribedFont } from '@/composables/useAppearanceOptions'
import { useSettingsStore } from '@/stores/settings'
import { DIAGRAM_HEIGHTS, NO_DIAGRAM_HEIGHT } from '@/constants/diagrams'
import {
  CODE_SIZES,
  NO_MEASURE,
  READING_MEASURES,
  READING_SIZES,
  READING_WEIGHTS,
} from '@/constants/fonts'

const { t } = useI18n()
const settings = useSettingsStore()
const { codeVariants, diagramAligns, diagramThemes, readingFonts, headingFonts, monoFonts, diagramFonts } =
  useAppearanceOptions()

// Each option is set in the typeface it selects: a family's name says less than its shapes.
function optionProps(option: DescribedFont) {
  return { style: { fontFamily: option.stack } }
}

const sizeOptions = READING_SIZES.map((size) => ({ title: `${size} px`, value: size }))

const codeSizeOptions = CODE_SIZES.map((size) => ({ title: `${size} px`, value: size }))

// The same trick as with typefaces: an option is set in its own weight, not just named by a number.
const weightOptions = READING_WEIGHTS.map((weight) => ({
  title: String(weight),
  value: weight,
  props: { style: { fontWeight: weight } },
}))

const measureOptions = computed(() =>
  READING_MEASURES.map((measure) => ({
    title: measure === NO_MEASURE ? t('settings.interface.measure.reading.unlimited') : `${measure}ch`,
    value: measure,
  })),
)

const diagramHeightOptions = computed(() =>
  DIAGRAM_HEIGHTS.map((height) => ({
    title: height === NO_DIAGRAM_HEIGHT ? t('settings.interface.diagram.height.unlimited') : `${height} px`,
    value: height,
  })),
)
</script>

<template>
  <VCard variant="outlined" rounded="lg" class="doc-appearance">
    <div class="doc-appearance__fields scroll-y">
      <p class="doc-appearance__title">{{ t('settings.interface.group.document.title') }}</p>

      <VSelectStepper
        v-model="settings.typography.readingFont"
        :items="readingFonts"
        item-title="label"
        item-value="code"
        :item-props="optionProps"
        :chips="false"
        :label="t('settings.interface.font.reading.label')"
        variant="outlined"
        density="compact"
        hide-details
      />
      <VSelectStepper
        v-model="settings.typography.readingSize"
        :items="sizeOptions"
        :chips="false"
        :label="t('settings.interface.size.reading.label')"
        variant="outlined"
        density="compact"
        hide-details
      />
      <VSelectStepper
        v-model="settings.typography.readingWeight"
        :items="weightOptions"
        :chips="false"
        :label="t('settings.interface.weight.reading.label')"
        variant="outlined"
        density="compact"
        hide-details
      />
      <VSelectStepper
        v-model="settings.typography.headingFont"
        :items="headingFonts"
        item-title="label"
        item-value="code"
        :item-props="optionProps"
        :chips="false"
        :label="t('settings.interface.font.heading.label')"
        variant="outlined"
        density="compact"
        hide-details
      />
      <VSelectStepper
        v-model="settings.typography.headingWeight"
        :items="weightOptions"
        :chips="false"
        :label="t('settings.interface.weight.heading.label')"
        variant="outlined"
        density="compact"
        hide-details
      />
      <VSelectStepper
        v-model="settings.typography.readingMeasure"
        :items="measureOptions"
        :chips="false"
        :label="t('settings.interface.measure.reading.label')"
        variant="outlined"
        density="compact"
        hide-details
      />

      <p class="doc-appearance__title">{{ t('settings.interface.group.code.title') }}</p>

      <VSelect
        v-model="settings.typography.codeVariant"
        :items="codeVariants"
        item-title="label"
        item-value="code"
        :chips="false"
        :label="t('settings.interface.code.variant.label')"
        variant="outlined"
        density="compact"
        hide-details
      />
      <VSelectStepper
        v-model="settings.typography.monoFont"
        :items="monoFonts"
        item-title="label"
        item-value="code"
        :item-props="optionProps"
        :chips="false"
        :label="t('settings.interface.font.mono.label')"
        variant="outlined"
        density="compact"
        hide-details
      />
      <VSelectStepper
        v-model="settings.typography.codeSize"
        :items="codeSizeOptions"
        :chips="false"
        :label="t('settings.interface.size.code.label')"
        variant="outlined"
        density="compact"
        hide-details
      />
      <!-- A panel without a background: the card gives it frame and spacing, and its own outline
           inside the field list would read as a nested block. -->
      <SwitchPanel
        v-model="settings.typography.codeLineNumbers"
        tone="transparent"
        :title="t('settings.interface.code.line_numbers.label')"
      />

      <p class="doc-appearance__title">{{ t('settings.interface.group.diagram.title') }}</p>

      <VSelect
        v-model="settings.diagrams.theme"
        :items="diagramThemes"
        item-title="label"
        item-value="code"
        :chips="false"
        :label="t('settings.interface.diagram.theme.label')"
        variant="outlined"
        density="compact"
        hide-details
      />
      <VSelect
        v-model="settings.diagrams.font"
        :items="diagramFonts"
        item-title="label"
        item-value="code"
        :item-props="optionProps"
        :chips="false"
        :label="t('settings.interface.font.diagram.label')"
        variant="outlined"
        density="compact"
        hide-details
      />
      <VSelect
        v-model="settings.diagrams.align"
        :items="diagramAligns"
        item-title="label"
        item-value="code"
        :chips="false"
        :label="t('settings.interface.diagram.align.label')"
        variant="outlined"
        density="compact"
        hide-details
      />
      <VSelect
        v-model="settings.diagrams.maxHeight"
        :items="diagramHeightOptions"
        :chips="false"
        :label="t('settings.interface.diagram.height.label')"
        variant="outlined"
        density="compact"
        hide-details
      />
    </div>
  </VCard>
</template>

<style scoped>
/* The card isn't squeezed by its neighbours (`flex: none`), but doesn't grow endlessly either:
   fourteen fields are taller than any rail, so the height is capped at a share of the screen and
   the rest scrolls INSIDE the frame. Without a cap the card would push the table of contents below
   it out of the rail entirely. */
.doc-appearance {
  padding: 0;
  margin-bottom: 12px;
  display: flex;
  flex: none;
  max-height: 45vh;
  min-width: 0;
}

/* The padding belongs to the scrolling strip, not the card: otherwise the scrollbar would sit
   inside the padding, 12px from the frame's edge. */
.doc-appearance__fields {
  display: flex;
  flex: 1;
  flex-direction: column;
  gap: 16px;
  padding: 12px;
  min-width: 0;
  min-height: 0;
}

/* A group heading, not a section heading: the rail is not the settings page, and the caption here
   only names what the fields below control. The first sits at the edge, the others get a bit more
   air above than between fields, so groups read as groups. */
.doc-appearance__title {
  margin: 0;
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--text-faint);
}

.doc-appearance__title:not(:first-child) {
  margin-top: 8px;
}

/* Narrow screen: the rail stops being sticky and sits above the content, nothing else shares the
   screen height with it — the cap is lifted and the fields flow in sequence. Scrolling inside the
   card there would be a second scroll on a page that already scrolls. */
@media (max-width: 1099px) {
  .doc-appearance {
    max-height: none;
  }
}
</style>
