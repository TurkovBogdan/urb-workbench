<script setup lang="ts">
import { onActivated, reactive, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { IconRefresh, IconDeviceFloppy } from '@tabler/icons-vue'

import PageLayout from '@/layout/templates/PageLayout.vue'
import PageHeader from '@/layout/components/PageHeader.vue'
import SwitchPanel from '@/components/SwitchPanel.vue'
import { errorText } from '@/api/errorText'
import { getSetup, applySetup, isBackendUp, type SetupGroup, type SetupField } from '../api'
import { useSetupLabels } from '../labels'

const { t } = useI18n()
const { groupTitle, fieldLabel, fieldDescription } = useSetupLabels()

const groups = ref<SetupGroup[]>([])
// Local working copy: { ENV_KEY: string value }.
const values = reactive<Record<string, string>>({})

const loading = ref(true)
const error = ref<string | null>(null)
const applying = ref(false)
const restarting = ref(false)

async function load() {
  loading.value = true
  error.value = null
  try {
    const payload = await getSetup()
    groups.value = payload.groups
    for (const group of payload.groups)
      for (const field of group.fields) values[field.key] = field.value
  } catch (e) {
    error.value = errorText(e)
  } finally {
    loading.value = false
  }
}

onActivated(load)

// Visibility reacts to the form selection: postgres fields are hidden under sqlite and vice versa.
function visibleFields(group: SetupGroup): SetupField[] {
  return group.fields.filter(
    (f) => !f.visible_when || values[f.visible_when.key] === f.visible_when.equals,
  )
}

// The switch panel carries the description inside itself, next to the title; the regular caption
// below would be a second copy of the same text for such a field.
function hasCaptionBelow(field: SetupField): boolean {
  return Boolean(field.description) && field.type !== 'bool'
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => window.setTimeout(resolve, ms))
}

async function waitForRestart() {
  await sleep(1000)
  for (let attempt = 0; attempt < 30; attempt++) {
    if (await isBackendUp()) {
      window.location.reload()
      return
    }
    await sleep(1000)
  }
  restarting.value = false
  error.value = t('setup.error.restart_timeout')
}

async function apply() {
  applying.value = true
  error.value = null
  try {
    await applySetup({ ...values })
    applying.value = false
    restarting.value = true
    await waitForRestart()
  } catch (e) {
    error.value = errorText(e)
    applying.value = false
  }
}
</script>

<template>
  <PageLayout>
    <PageHeader
      :title="t('setup.page.title')"
      :description="t('setup.page.description')"
    >
      <template #actions>
        <VBtn variant="text" :disabled="loading || applying || restarting" @click="load">
          <template #prepend><IconRefresh :size="16" /></template>
          {{ t('setup.action.refresh') }}
        </VBtn>
        <VBtn
          color="primary"
          :loading="applying"
          :disabled="restarting"
          @click="apply"
        >
          <template #prepend><IconDeviceFloppy :size="18" /></template>
          {{ t('setup.action.apply') }}
        </VBtn>
      </template>
    </PageHeader>

    <div v-if="loading" class="d-flex justify-center py-12">
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

    <VAlert v-if="restarting" type="info" variant="tonal" class="mb-4">
      <div class="d-flex align-center ga-3">
        <VProgressCircular indeterminate size="20" width="2" />
        {{ t('setup.status.restarting') }}
      </div>
    </VAlert>

    <template v-if="!loading">
      <div class="setup-grid">
        <VCard
          v-for="group in groups"
          :key="group.code"
          variant="outlined"
          rounded="lg"
          class="setup-card"
        >
          <VCardTitle class="text-h6">{{ groupTitle(group) }}</VCardTitle>
          <VDivider />
          <VCardText class="d-flex flex-column ga-4">
            <div
              v-for="field in visibleFields(group)"
              :key="field.key"
              class="d-flex flex-column"
            >
              <VSelect
                v-if="field.type === 'choice'"
                v-model="values[field.key]"
                :items="field.choices"
                :label="fieldLabel(field)"
                :disabled="applying || restarting"
                density="comfortable"
                hide-details
              />
              <SwitchPanel
                v-else-if="field.type === 'bool'"
                :model-value="values[field.key] === 'true'"
                :title="fieldLabel(field)"
                :description="fieldDescription(field)"
                :disabled="applying || restarting"
                @update:model-value="values[field.key] = String($event)"
              />
              <VTextField
                v-else
                v-model="values[field.key]"
                :label="fieldLabel(field)"
                :type="field.type === 'int' ? 'number' : field.secret ? 'password' : 'text'"
                :disabled="applying || restarting"
                density="comfortable"
                hide-details
              />
              <span
                v-if="hasCaptionBelow(field)"
                class="text-caption text-medium-emphasis mt-1"
              >
                {{ fieldDescription(field) }}
              </span>
            </div>
          </VCardText>
        </VCard>
      </div>
    </template>
  </PageLayout>
</template>

<style scoped>
/* Columns, not a single stack: there are few groups, and on a wide screen a full-width card
   drives the eye across empty space from a field's label to its value.
   `minmax(320, 440)` — the column's upper bound: an input wider than ~440px reads worse, not
   better, so extra width goes to the neighbouring column instead of stretching the card. The
   number is chosen so that TWO columns fit at the typical content width (~930px): 460 gave
   936px for the pair and collapsed the layout back into a stack.
   `align-items: start` — each card is as tall as its content; without it the grid stretches
   every card in a row to the tallest, and a short one gets an empty bottom. */
.setup-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(320px, 440px));
  align-items: start;
  justify-content: start;
  gap: 16px;
}

/* One column on a narrow screen — otherwise the fields shrink until unreadable. */
@media (max-width: 700px) {
  .setup-grid {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
