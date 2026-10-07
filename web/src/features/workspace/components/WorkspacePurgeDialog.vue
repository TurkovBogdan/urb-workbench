<script setup lang="ts">
// Permanent deletion: the workspace row leaves the database together with everything the modules
// on top kept in it, and there is no "restore" after that.
//
// A separate dialog, not a checkbox in the regular delete: the irreversible must not differ from
// the reversible by one toggle. There is no typed confirmation: the item is reachable only from the
// trash — a workspace is soft-deleted first — so the purge is already the second deliberate step,
// and the dialog's job is to say plainly what goes with it.
//
// The text names task groups and tasks although this module does not own them: that is what lies
// inside a workspace in this application, and "everything inside" told the person nothing. The
// numbers still come from the declared counters (`content.ts`).
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'

import AppDialog from '@/components/AppDialog.vue'
import { errorText } from '@/api/errorText'

import { purgeWorkspace, type WorkspaceListRow } from '../api'
import { contentSummary, hasContent } from '../content'

const open = defineModel<boolean>({ required: true })

const props = defineProps<{ workspace: WorkspaceListRow | null }>()
const emit = defineEmits<{ purged: [] }>()

const { t } = useI18n()

const busy = ref(false)
const error = ref<string | null>(null)

const filled = computed(() => hasContent(props.workspace))
const summary = computed(() => contentSummary(props.workspace, t))

watch(open, (isOpen) => {
  if (!isOpen) return
  error.value = null
})

async function purge() {
  if (!props.workspace) return
  busy.value = true
  error.value = null
  try {
    // The failure is shown in the dialog: the person is looking here and decides what to do here.
    await purgeWorkspace(props.workspace.code, { report: false })
    open.value = false
    emit('purged')
  } catch (e) {
    error.value = errorText(e)
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <AppDialog
    v-model="open"
    :title="t('workspace.purge.title')"
    :description="props.workspace?.title"
    size="narrow"
    :persistent="busy"
    :close-disabled="busy"
  >
    <div class="workspace-purge">
      <!-- Plain text, as in the soft delete: the red "Delete forever" button and the title already
           say this is final, and a red block on top of them would shout the same thing twice. -->
      <p class="workspace-purge__text">
        {{ filled
          ? t('workspace.purge.with_content', { content: summary })
          : t('workspace.purge.empty') }}
      </p>

      <VAlert v-if="error" type="error" variant="tonal" density="compact">{{ error }}</VAlert>
    </div>

    <template #actions>
      <VBtn variant="text" :disabled="busy" @click="open = false">
        {{ t('common.action.cancel') }}
      </VBtn>
      <VBtn color="error" variant="flat" :loading="busy" @click="purge">
        {{ t('workspace.purge.submit') }}
      </VBtn>
    </template>
  </AppDialog>
</template>

<style scoped>
.workspace-purge {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

/* The type of the soft delete's question line (`WorkspaceDeleteDialog`). */
.workspace-purge__text {
  margin: 0;
  font-size: 14px;
  line-height: 1.5;
  color: var(--text);
}
</style>
