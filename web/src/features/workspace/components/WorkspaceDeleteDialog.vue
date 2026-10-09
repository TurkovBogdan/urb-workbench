<script setup lang="ts">
// Soft delete of a workspace: how much is inside, what exactly the click changes, and how to undo
// it from the trash filter. The notification the page shows after carries its own "Restore" and
// needs no mention here.
//
// The numbers come from the list row rather than being requested on open: they already arrived
// with the list, and a second request would show the same thing a frame later. Without them the
// dialog would ask to confirm the unknown — "the content will stay" is no answer to "how much of
// it is there".
//
// The enumeration is assembled from the counters (`content.ts`), not written in the dictionary:
// the modules on top know what exactly lies inside, and the next one must not have to edit this
// phrase.
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'

import AppDialog from '@/components/AppDialog.vue'
import { errorText } from '@/api/errorText'

import { deleteWorkspace, type WorkspaceListRow } from '../api'
import { contentSummary, hasContent } from '../content'

const open = defineModel<boolean>({ required: true })

const props = defineProps<{ workspace: WorkspaceListRow | null }>()
/** The deleted workspace goes out: the page offers to bring exactly it back. */
const emit = defineEmits<{ deleted: [workspace: WorkspaceListRow] }>()

const { t } = useI18n()

const busy = ref(false)
const error = ref<string | null>(null)

const filled = computed(() => hasContent(props.workspace))
const summary = computed(() => contentSummary(props.workspace, t))

watch(open, (isOpen) => {
  if (!isOpen) return
  error.value = null
})

async function remove() {
  const workspace = props.workspace
  if (!workspace) return
  busy.value = true
  error.value = null
  try {
    // The failure is shown in the dialog, not as a toast: the person is looking here and decides
    // what to do right here.
    await deleteWorkspace(workspace.code, { report: false })
    open.value = false
    emit('deleted', workspace)
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
    :title="t('workspace.delete.title')"
    :description="props.workspace?.title"
    size="narrow"
    :persistent="busy"
    :close-disabled="busy"
  >
    <div class="workspace-delete">
      <p class="workspace-delete__text">
        {{ filled
          ? t('workspace.delete.with_content', { content: summary })
          : t('workspace.delete.empty') }}
      </p>

      <!-- What the click changes, one consequence per line: where the workspace stops being seen,
           what becomes of its content, and what agents notice. The agents' line is precise on
           purpose — a connection already bound to it keeps working, only a new one cannot pick it
           (`workspace_use` refuses a deleted workspace, `require_active` does not). -->
      <div class="workspace-delete__effects">
        <span class="workspace-delete__label">{{ t('workspace.delete.effects') }}</span>
        <ul class="workspace-delete__list">
          <li>{{ t('workspace.delete.hidden') }}</li>
          <li v-if="filled">{{ t('workspace.delete.content_kept') }}</li>
          <li>{{ t('workspace.delete.agents') }}</li>
        </ul>
      </div>

      <!-- How to undo, on a separate muted line: it is not a warning but what removes the fear of
           the button. Merge it into the list and it gets lost. -->
      <p class="workspace-delete__note">{{ t('workspace.delete.restore_hint') }}</p>

      <VAlert v-if="error" type="error" variant="tonal" density="compact">{{ error }}</VAlert>
    </div>

    <template #actions>
      <VBtn variant="text" :disabled="busy" @click="open = false">
        {{ t('common.action.cancel') }}
      </VBtn>
      <VBtn color="error" variant="flat" :loading="busy" @click="remove">
        {{ t('workspace.delete.submit') }}
      </VBtn>
    </template>
  </AppDialog>
</template>

<style scoped>
.workspace-delete {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.workspace-delete__text {
  margin: 0;
  font-size: 14px;
  line-height: 1.5;
  color: var(--text);
}

.workspace-delete__effects {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.workspace-delete__label {
  font-size: 12px;
  color: var(--text-muted);
}

.workspace-delete__list {
  margin: 0;
  padding-left: 18px;
  display: flex;
  flex-direction: column;
  gap: 4px;
  font-size: 13px;
  line-height: 1.45;
  color: var(--text);
}

.workspace-delete__note {
  margin: 0;
  font-size: 12px;
  line-height: 1.45;
  color: var(--text-muted);
}
</style>
