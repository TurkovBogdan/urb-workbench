<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

import PageLayout from '@/layout/templates/PageLayout.vue'
import PageHeader from '@/layout/components/PageHeader.vue'
import MarkdownRenderer from '@/components/markdown/renderer/MarkdownRenderer.vue'
import SettingsGroup from '@/components/settings/SettingsGroup.vue'
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
import { LANGUAGE_OPTIONS, flagUrl } from '@/constants/language'
import { PREVIEWS } from '../previews'

// The app's appearance. Unlike `/settings/modules` there is no save button here: a choice applies
// instantly and goes to the database (the `core_interface` module) by itself — in a batch, half a
// second after the last move. Hence no "unsaved" state either.
//
// They are still laid out like module settings — groups with an explanation, a field and a caption
// under it, and a switch is a panel (`SwitchPanel`), the same one a schema bool field renders. The
// field set here is known in place and heterogeneous, so the cards are written as markup rather
// than built by looping over a schema: a schema is needed where fields come from the backend.
const { t } = useI18n()
const settings = useSettingsStore()

const {
  themes,
  codeVariants,
  diagramAligns,
  diagramThemes,
  interfaceFonts,
  readingFonts,
  headingFonts,
  monoFonts,
  diagramFonts,
} = useAppearanceOptions()

// The samples are markdown and go through the real renderer, so each preview is the reading zone
// itself rather than an imitation of it.
const preview = computed(() => PREVIEWS[settings.locale.language])

// Each option previews itself: the row is set in the family it selects, which tells more
// than its name does, and the note says what the family is for.
function optionProps(option: DescribedFont) {
  return { subtitle: option.note, style: { fontFamily: option.stack } }
}

function noteProps(option: { note: string }) {
  return { subtitle: option.note }
}

const diagramHeightOptions = computed(() =>
  DIAGRAM_HEIGHTS.map((height) => ({
    title: height === NO_DIAGRAM_HEIGHT ? t('settings.interface.diagram.height.unlimited') : `${height} px`,
    value: height,
  })),
)

const sizeOptions = READING_SIZES.map((size) => ({ title: `${size} px`, value: size }))

const codeSizeOptions = CODE_SIZES.map((size) => ({ title: `${size} px`, value: size }))

// Each option is set in its own weight: seeing the weight matters more than reading its number.
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

</script>

<template>
  <PageLayout>
    <PageHeader
      :title="t('settings.interface.page.title')"
      :description="t('settings.interface.page.description')"
    />

    <div class="settings-list">
      <SettingsGroup
        :title="t('settings.interface.group.app.title')"
        :description="t('settings.interface.group.app.description')"
      >
        <div class="setting">
          <VSelect
            v-model="settings.locale.language"
            :items="LANGUAGE_OPTIONS"
            item-title="label"
            item-value="code"
            :chips="false"
            :label="t('settings.interface.language.label')"
            variant="outlined"
            density="comfortable"
            hide-details="auto"
          >
            <template #selection="{ item }">
              <img v-if="flagUrl(item.flag)" :src="flagUrl(item.flag)" alt="" class="language-flag" />
              <span>{{ item.label }}</span>
            </template>
            <template #item="{ props: itemProps, item }">
              <VListItem v-bind="itemProps">
                <template #prepend>
                  <img v-if="flagUrl(item.flag)" :src="flagUrl(item.flag)" alt="" class="language-flag" />
                </template>
              </VListItem>
            </template>
          </VSelect>
          <p class="setting__desc">{{ t('settings.interface.language.description') }}</p>
        </div>

        <div class="setting">
          <VSelect
            v-model="settings.appearance.theme"
            :items="themes"
            item-title="label"
            item-value="code"
            :item-props="noteProps"
            :chips="false"
            :label="t('settings.interface.theme.label')"
            variant="outlined"
            density="comfortable"
            hide-details="auto"
          />
          <p class="setting__desc">{{ t('settings.interface.theme.description') }}</p>
        </div>

        <div class="setting">
          <VSelectStepper
            v-model="settings.typography.interfaceFont"
            :items="interfaceFonts"
            item-title="label"
            item-value="code"
            :item-props="optionProps"
            :chips="false"
            :label="t('settings.interface.font.interface.label')"
            variant="outlined"
            density="comfortable"
            hide-details="auto"
          />
          <p class="setting__desc">{{ t('settings.interface.font.interface.description') }}</p>
        </div>
      </SettingsGroup>

      <SettingsGroup
        :title="t('settings.interface.group.document.title')"
        :description="t('settings.interface.group.document.description')"
      >
        <div class="setting">
          <VSelectStepper
            v-model="settings.typography.readingFont"
            :items="readingFonts"
            item-title="label"
            item-value="code"
            :item-props="optionProps"
            :chips="false"
            :label="t('settings.interface.font.reading.label')"
            variant="outlined"
            density="comfortable"
            hide-details="auto"
          />
          <p class="setting__desc">{{ t('settings.interface.font.reading.description') }}</p>
        </div>

        <div class="setting">
          <VSelectStepper
            v-model="settings.typography.readingSize"
            :items="sizeOptions"
            :chips="false"
            :label="t('settings.interface.size.reading.label')"
            variant="outlined"
            density="comfortable"
            hide-details="auto"
          />
          <p class="setting__desc">{{ t('settings.interface.size.reading.description') }}</p>
        </div>

        <div class="setting">
          <VSelectStepper
            v-model="settings.typography.readingWeight"
            :items="weightOptions"
            :chips="false"
            :label="t('settings.interface.weight.reading.label')"
            variant="outlined"
            density="comfortable"
            hide-details="auto"
          />
          <p class="setting__desc">{{ t('settings.interface.weight.reading.description') }}</p>
        </div>

        <div class="setting">
          <VSelectStepper
            v-model="settings.typography.headingFont"
            :items="headingFonts"
            item-title="label"
            item-value="code"
            :item-props="optionProps"
            :chips="false"
            :label="t('settings.interface.font.heading.label')"
            variant="outlined"
            density="comfortable"
            hide-details="auto"
          />
          <p class="setting__desc">{{ t('settings.interface.font.heading.description') }}</p>
        </div>

        <div class="setting">
          <VSelectStepper
            v-model="settings.typography.headingWeight"
            :items="weightOptions"
            :chips="false"
            :label="t('settings.interface.weight.heading.label')"
            variant="outlined"
            density="comfortable"
            hide-details="auto"
          />
          <p class="setting__desc">{{ t('settings.interface.weight.heading.description') }}</p>
        </div>

        <div class="setting">
          <VSelectStepper
            v-model="settings.typography.readingMeasure"
            :items="measureOptions"
            :chips="false"
            :label="t('settings.interface.measure.reading.label')"
            variant="outlined"
            density="comfortable"
            hide-details="auto"
          />
          <p class="setting__desc">{{ t('settings.interface.measure.reading.description') }}</p>
        </div>

      </SettingsGroup>

      <!-- The sample document sits right after the settings that apply to it: typeface, size and
           column width are chosen by how they read, not by their name in a list. It updates live —
           a choice reaches the reading zone at the same instant as the rest of the app. -->
      <VCard variant="outlined" rounded="lg">
        <VCardTitle class="text-h6">{{ t('settings.interface.preview.title') }}</VCardTitle>
        <VDivider />
        <VCardText>
          <MarkdownRenderer :text="preview.document" />
        </VCardText>
      </VCard>

      <SettingsGroup
        :title="t('settings.interface.group.code.title')"
        :description="t('settings.interface.group.code.description')"
      >
        <div class="setting">
          <VSelect
            v-model="settings.typography.codeVariant"
            :items="codeVariants"
            item-title="label"
            item-value="code"
            :item-props="noteProps"
            :chips="false"
            :label="t('settings.interface.code.variant.label')"
            variant="outlined"
            density="comfortable"
            hide-details="auto"
          />
          <p class="setting__desc">{{ t('settings.interface.code.variant.description') }}</p>
        </div>

        <div class="setting">
          <VSelectStepper
            v-model="settings.typography.monoFont"
            :items="monoFonts"
            item-title="label"
            item-value="code"
            :item-props="optionProps"
            :chips="false"
            :label="t('settings.interface.font.mono.label')"
            variant="outlined"
            density="comfortable"
            hide-details="auto"
          />
          <p class="setting__desc">{{ t('settings.interface.font.mono.description') }}</p>
        </div>

        <div class="setting">
          <VSelectStepper
            v-model="settings.typography.codeSize"
            :items="codeSizeOptions"
            :chips="false"
            :label="t('settings.interface.size.code.label')"
            variant="outlined"
            density="comfortable"
            hide-details="auto"
          />
          <p class="setting__desc">{{ t('settings.interface.size.code.description') }}</p>
        </div>

        <SwitchPanel
          v-model="settings.typography.codeLineNumbers"
          :title="t('settings.interface.code.line_numbers.label')"
          :description="t('settings.interface.code.line_numbers.description')"
        />
      </SettingsGroup>

      <VCard variant="outlined" rounded="lg">
        <VCardTitle class="text-h6">{{ t('settings.interface.preview.title') }}</VCardTitle>
        <VDivider />
        <VCardText>
          <MarkdownRenderer :text="preview.code" />
        </VCardText>
      </VCard>

      <SettingsGroup
        :title="t('settings.interface.group.diagram.title')"
        :description="t('settings.interface.group.diagram.description')"
      >
        <div class="setting">
          <VSelect
            v-model="settings.diagrams.theme"
            :items="diagramThemes"
            item-title="label"
            item-value="code"
            :item-props="noteProps"
            :chips="false"
            :label="t('settings.interface.diagram.theme.label')"
            variant="outlined"
            density="comfortable"
            hide-details="auto"
          />
          <p class="setting__desc">{{ t('settings.interface.diagram.theme.description') }}</p>
        </div>

        <div class="setting">
          <VSelect
            v-model="settings.diagrams.font"
            :items="diagramFonts"
            item-title="label"
            item-value="code"
            :item-props="optionProps"
            :chips="false"
            :label="t('settings.interface.font.diagram.label')"
            variant="outlined"
            density="comfortable"
            hide-details="auto"
          />
          <p class="setting__desc">{{ t('settings.interface.font.diagram.description') }}</p>
        </div>

        <div class="setting">
          <VSelect
            v-model="settings.diagrams.align"
            :items="diagramAligns"
            item-title="label"
            item-value="code"
            :item-props="noteProps"
            :chips="false"
            :label="t('settings.interface.diagram.align.label')"
            variant="outlined"
            density="comfortable"
            hide-details="auto"
          />
          <p class="setting__desc">{{ t('settings.interface.diagram.align.description') }}</p>
        </div>

        <div class="setting">
          <VSelect
            v-model="settings.diagrams.maxHeight"
            :items="diagramHeightOptions"
            :chips="false"
            :label="t('settings.interface.diagram.height.label')"
            variant="outlined"
            density="comfortable"
            hide-details="auto"
          />
          <p class="setting__desc">{{ t('settings.interface.diagram.height.description') }}</p>
        </div>
      </SettingsGroup>

      <VCard variant="outlined" rounded="lg">
        <VCardTitle class="text-h6">{{ t('settings.interface.preview.title') }}</VCardTitle>
        <VDivider />
        <VCardText>
          <MarkdownRenderer :text="preview.diagram" />
        </VCardText>
      </VCard>
    </div>
  </PageLayout>
</template>

<style scoped>
/* The same layout as the module cards: a group card spans the full page width, groups stack, and
   the fields inside are laid out in columns (the `.settings-columns` utility). */
.settings-list {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

/* A caption under the field, not a Vuetify hint: module settings keep the description as a
   separate line under the field, and client settings must not look like a different kind of
   setting. */
.setting {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.setting__desc {
  margin: 0;
  font-size: 12px;
  line-height: 1.4;
  color: var(--text-muted);
}

.language-flag {
  width: 20px;
  height: 20px;
  margin-inline-end: 10px;
  flex: 0 0 auto;
  vertical-align: middle;
}
</style>
