<script setup lang="ts">
import { computed, onActivated, reactive, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { IconRotate, IconDeviceFloppy } from '@tabler/icons-vue'

import PageLayout from '@/layout/templates/PageLayout.vue'
import PageHeader from '@/layout/components/PageHeader.vue'
import MarkdownRenderer from '@/components/markdown/renderer/MarkdownRenderer.vue'
import SettingField from '@/components/settings/SettingField.vue'
import type { FieldDescriptor } from '@/shared/settings-fields'
import { errorText } from '@/api/errorText'
import { useSettingLabels } from '../labels'
import { listModules, putValue, type ModulePayload } from '../api'

/** A block of fields on screen: either with its own caption or headed by a switch. */
interface FieldBlock {
  key: string
  /** The block caption. Empty when the switch in the header plays its role. */
  caption: string
  /** A bool field lifted into the block header: the other fields read as its content. */
  header: FieldDescriptor | null
  fields: FieldDescriptor[]
}

const { t } = useI18n()
const { localizeField } = useSettingLabels()

// Module names in the card headers: a label is needed where the module name reads worse than the
// section name. Without a key the name is shown as is, so an empty map is legitimate.
// It is empty now: no module in this build declares settings, and the former three entries
// (`hh`, `core_connectors`, `web_search`) outlived their modules.
const MODULE_LABELS: Record<string, string> = {}

const modules = ref<ModulePayload[]>([])
const loading = ref(true)
const refreshing = ref(false)
const saving = ref(false)
const error = ref<string | null>(null)
// values — the editable copy; saved — the server snapshot for change detection.
const values = reactive<Record<string, Record<string, unknown>>>({})
const saved = reactive<Record<string, Record<string, unknown>>>({})
// Per-field validation errors (filled on save).
const fieldErrors = reactive<Record<string, Record<string, string | null>>>({})

function moduleLabel(name: string): string {
  return MODULE_LABELS[name] ?? name
}

// Field label/description are backend-owned; translate them at render time so the
// switch is live. Re-runs on locale change (localizeField reads the reactive locale).
const localizedModules = computed(() =>
  modules.value.map((m) => ({
    ...m,
    fields: m.fields.map((f) => localizeField(m.module, f)),
  })),
)

// The visibility condition is evaluated against the CURRENT form, not the saved one: switch a
// service off and its key goes away at once, without waiting for save. A hidden field is not
// erased and comes back with the condition.
function visible(module: string, field: FieldDescriptor): boolean {
  const condition = field.visible_when
  return condition === null || values[module]?.[condition.key] === condition.equals
}

// Fields of one group come consecutively in the schema, so a block closes at the first field of a
// different group — no sorting or bucketing by dictionary is needed: schema order is screen order.
function splitByGroup(fields: FieldDescriptor[]): FieldDescriptor[][] {
  const blocks: FieldDescriptor[][] = []
  for (const field of fields) {
    const sameGroupAsPrevious = blocks.length > 0 && blocks[blocks.length - 1][0].group === field.group
    if (sameGroupAsPrevious) blocks[blocks.length - 1].push(field)
    else blocks.push([field])
  }
  return blocks
}

// A switch heading a group ("Enable Tavily") names the block itself, so no caption is rendered
// with it — otherwise the service name would appear twice in a row.
function toBlock(module: string, group: FieldDescriptor[]): FieldBlock {
  const [first, ...rest] = group
  const headed = first.group !== '' && first.kind === 'bool'
  return {
    key: `${first.group}:${first.key}`,
    caption: headed ? '' : first.group,
    header: headed ? first : null,
    fields: (headed ? rest : group).filter((f) => visible(module, f)),
  }
}

const moduleBlocks = computed(() =>
  localizedModules.value.map((m) => ({
    ...m,
    blocks: splitByGroup(m.fields)
      .map((group) => toBlock(m.module, group))
      // A group with everything hidden and no switch must not leave an empty frame.
      .filter((b) => b.header !== null || b.fields.length > 0),
  })),
)

function changed(module: string, key: string): boolean {
  return JSON.stringify(values[module]?.[key]) !== JSON.stringify(saved[module]?.[key])
}

function snapshot(module: string, serverValues: Record<string, unknown>) {
  values[module] = { ...serverValues }
  saved[module] = { ...serverValues }
  fieldErrors[module] = {}
}

async function load() {
  refreshing.value = true
  error.value = null
  try {
    const list = await listModules()
    modules.value = list
    for (const m of list) snapshot(m.module, m.values)
  } catch (e) {
    error.value = errorText(e)
  } finally {
    refreshing.value = false
  }
}

onActivated(async () => {
  await load()
  loading.value = false
})

function onChange(module: string, key: string, value: unknown) {
  values[module] = { ...values[module], [key]: value }
  fieldErrors[module][key] = null
}

// A single "Save" button: we write ALL changed fields. The entered value stays in the field
// (the snapshot moves onto it), and the page is NOT reloaded — otherwise the secret would come
// back as a sentinel and "erase" the token just typed into the field. A fresh sentinel arrives
// on the next page open.
async function saveAll() {
  saving.value = true
  error.value = null
  let hadError = false
  for (const m of modules.value) {
    for (const f of m.fields) {
      if (!changed(m.module, f.key)) continue
      try {
        await putValue(m.module, f.key, values[m.module][f.key])
        saved[m.module][f.key] = values[m.module][f.key]
        fieldErrors[m.module][f.key] = null
      } catch (e) {
        hadError = true
        fieldErrors[m.module][f.key] = errorText(e)
      }
    }
  }
  saving.value = false
  if (hadError) error.value = t('settings.error.save_failed')
}
</script>

<template>
  <PageLayout>
    <PageHeader
      :title="t('settings.page.title')"
      :description="t('settings.page.description')"
    >
      <template #actions>
        <VBtn
          variant="text"
          :disabled="refreshing || saving"
          @click="load"
        >
          <template #prepend><IconRotate :size="16" :class="{ 'icon-spin': refreshing }" /></template>
          {{ t('settings.action.discard') }}
        </VBtn>
        <VBtn
          color="primary"
          :loading="saving"
          @click="saveAll"
        >
          <template #prepend><IconDeviceFloppy :size="18" /></template>
          {{ t('settings.action.save') }}
        </VBtn>
      </template>
    </PageHeader>

    <div v-if="loading" class="d-flex justify-center align-center py-12">
      <VProgressCircular indeterminate size="32" width="2" />
    </div>

    <VAlert
      v-if="error"
      type="error"
      variant="tonal"
      closable
      class="mb-4"
      @click:close="error = null"
    >
      {{ error }}
    </VAlert>

    <div v-if="!loading" class="modules-list">
      <VCard
        v-for="m in moduleBlocks"
        :key="m.module"
        variant="outlined"
        rounded="lg"
      >
        <VCardTitle class="text-h6">{{ moduleLabel(m.module) }}</VCardTitle>
        <div v-if="m.description" class="module-desc">
          <MarkdownRenderer :text="m.description" compact />
        </div>
        <VDivider />
        <VCardText v-if="m.fields.length === 0" class="text-medium-emphasis">
          {{ t('settings.module.no_fields') }}
        </VCardText>
        <VCardText v-else class="d-flex flex-column ga-6">
          <div
            v-for="b in m.blocks"
            :key="b.key"
            class="field-block"
            :class="{ 'field-block--headed': b.header }"
          >
            <div v-if="b.caption" class="field-block__caption">{{ b.caption }}</div>

            <SettingField
              v-if="b.header"
              :field="b.header"
              :model-value="values[m.module]?.[b.header.key]"
              :error="fieldErrors[m.module]?.[b.header.key] ?? null"
              :saving="saving"
              @update:model-value="onChange(m.module, b.header.key, $event)"
            />

            <div v-if="b.fields.length" class="field-block__fields settings-columns">
              <SettingField
                v-for="f in b.fields"
                :key="f.key"
                :field="f"
                :model-value="values[m.module]?.[f.key]"
                :error="fieldErrors[m.module]?.[f.key] ?? null"
                :saving="saving"
                @update:model-value="onChange(m.module, f.key, $event)"
              />
            </div>
          </div>
        </VCardText>
      </VCard>
    </div>
  </PageLayout>
</template>

<style scoped>
/* A module card takes the full page width: the field block inside handles the column layout, and
   modules stack top to bottom in schema order. */
.modules-list {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

/* Block = a schema field group. Fields inside sit closer than blocks do to each other: the spacing
   is what makes the grouping readable, no separate frame is needed for it. */
.field-block {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

/* Fields under a switch are its content, not its neighbours: the indent and the rule on the left
   show that the key belongs to this particular service and goes away with it. The indent equals
   the switch width, so the fields line up under the panel's text, not under its edge. */
.field-block--headed .field-block__fields {
  margin-left: 14px;
  padding-left: 14px;
  border-left: 1px solid var(--border-soft);
}

.field-block__caption {
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  color: var(--text-muted);
}

.module-desc {
  padding: 0 16px 16px;
}
.module-desc :deep(.md-body) {
  font-size: 13px;
  line-height: 1.4;
  color: var(--text-muted);
}
.module-desc :deep(.md-body p) {
  margin: 0;
}
</style>
