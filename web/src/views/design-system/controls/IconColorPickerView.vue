<script setup lang="ts">
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'

import PageLayout from '@/layout/templates/PageLayout.vue'
import PageHeader from '@/layout/components/PageHeader.vue'
import IconColorPicker from '@/components/IconColorPicker.vue'
// The demo runs on the real sets — the app's palette and icons: made-up lists would show the
// layout on data the app doesn't have.
import { colorNames, colorVarsByName } from '@/shared/colors'
import { iconByName, iconNames } from '@/shared/icons'

const { t } = useI18n()

const icons = iconNames()
const colors = colorNames()

const icon = ref<string | null>('flask')
const color = ref<string | null>('teal')

const optionalIcon = ref<string | null>(null)
const optionalColor = ref<string | null>(null)

// What goes out, in the same literal form: a name is a string, "not selected" is `null`, and in
// the showcase the difference must be visible rather than inferred from an empty spot.
function modelLiteral(value: string | null): string {
  return value === null ? 'null' : `'${value}'`
}
</script>

<template>
  <PageLayout>
  <div class="ds-page">
    <PageHeader
      :title="t('design-system.page.icon-color-picker.title')"
      :description="t('design-system.page.icon-color-picker.description')"
      back-to="/design-system"
    />

    <section class="ds-section">
      <h6 class="mb-3">{{ t('design-system.section.icon-color-picker.basic') }}</h6>
      <div class="ds-card">
        <div class="ds-row">
          <span class="ds-tag">default</span>
          <div class="ds-controls ds-controls--stack">
            <IconColorPicker
              v-model:icon="icon"
              v-model:color="color"
              :icons="icons"
              :colors="colors"
              :resolve-icon="iconByName"
              :resolve-color="colorVarsByName"
            />
            <p class="ds-value">icon = {{ modelLiteral(icon) }} · color = {{ modelLiteral(color) }}</p>
          </div>
          <span class="ds-spec">v-model:icon, v-model:color</span>
        </div>

        <div class="ds-row">
          <span class="ds-tag">clearable</span>
          <div class="ds-controls ds-controls--stack">
            <IconColorPicker
              v-model:icon="optionalIcon"
              v-model:color="optionalColor"
              :icons="icons"
              :colors="colors"
              :resolve-icon="iconByName"
              :resolve-color="colorVarsByName"
              :height="140"
              clearable
            />
            <p class="ds-value">
              icon = {{ modelLiteral(optionalIcon) }} · color = {{ modelLiteral(optionalColor) }}
            </p>
          </div>
          <span class="ds-spec">clearable, :height="140"</span>
        </div>
      </div>
    </section>
  </div>
  </PageLayout>
</template>

<style scoped>
.ds-page { max-width: 860px; }

.ds-section { margin-bottom: 28px; }

.ds-card {
  background: var(--surface);
  border: 1px solid var(--border-soft);
  border-radius: var(--radius);
  overflow: hidden;
}

.ds-row {
  display: grid;
  grid-template-columns: 100px 1fr 200px;
  align-items: start;
  gap: 16px;
  padding: 12px 16px;
  border-bottom: 1px solid var(--border-soft);
}

.ds-row:last-child { border-bottom: none; }

.ds-tag {
  font-family: var(--font-mono);
  font-size: 11px;
  color: var(--text-faint);
  padding-top: 10px;
}

.ds-spec {
  font-family: var(--font-mono);
  font-size: 10px;
  color: var(--text-faint);
  text-align: right;
  padding-top: 10px;
}

/* The panel takes the full cell width: the tile grids derive their columns from it. */
.ds-controls--stack {
  display: block;
}

/* The live model value under the panel uses the same monospace as the prop labels on the right:
   both read as code, not as interface text. */
.ds-value {
  margin: 8px 0 0;
  font-family: var(--font-mono);
  font-size: 11px;
  color: var(--text-muted);
}
</style>
