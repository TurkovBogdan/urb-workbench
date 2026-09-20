<script setup lang="ts">
// Удаление навсегда: строка пространства уходит из базы вместе со всем, что держали в нём модули
// поверх, и никакого «восстановить» после этого нет.
//
// Отдельное окно, а не галочка в обычном удалении: необратимое не должно отличаться от
// обратимого одним тумблером. Подтверждение — ввод названия пространства: кнопка, до которой
// нельзя дойти не читая, и есть единственная защита там, где отменить нечем. Сверяем как есть,
// без обрезки и приведения регистра, — перепечатать имя целиком это и есть работа, ради которой
// поле стоит.
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

const confirmation = ref('')
const busy = ref(false)
const error = ref<string | null>(null)

const filled = computed(() => hasContent(props.workspace))
const summary = computed(() => contentSummary(props.workspace, t))

const confirmed = computed(
  () => Boolean(props.workspace) && confirmation.value === props.workspace?.title,
)

// Поле очищается на каждом открытии: подтверждение относится к одному конкретному сносу, и
// «оставшееся с прошлого раза» имя открыло бы окно уже разблокированным.
watch(open, (isOpen) => {
  if (!isOpen) return
  confirmation.value = ''
  error.value = null
})

async function purge() {
  if (!props.workspace || !confirmed.value) return
  busy.value = true
  error.value = null
  try {
    // Отказ показываем в окне: человек смотрит сюда и здесь же решает, что делать.
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
      <!-- Предупреждение алертом, а не абзацем, как в мягком удалении: там речь о том, что
           вернётся, здесь — о том, что не вернётся, и это должно бросаться в глаза. -->
      <VAlert type="error" variant="tonal" density="compact">
        {{ filled
          ? t('workspace.purge.with_content', { content: summary })
          : t('workspace.purge.empty') }}
      </VAlert>

      <p class="workspace-purge__hint">{{ t('workspace.purge.confirm_hint') }}</p>

      <VTextField
        v-model="confirmation"
        :label="t('workspace.purge.confirm_label')"
        :placeholder="props.workspace?.title"
        variant="outlined"
        autocomplete="off"
        hide-details
        autofocus
      />

      <VAlert v-if="error" type="error" variant="tonal" density="compact">{{ error }}</VAlert>
    </div>

    <template #actions>
      <VBtn variant="text" :disabled="busy" @click="open = false">
        {{ t('common.action.cancel') }}
      </VBtn>
      <VBtn
        color="error"
        variant="flat"
        :loading="busy"
        :disabled="!confirmed"
        @click="purge"
      >
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

.workspace-purge__hint {
  margin: 0;
  font-size: 13px;
  line-height: 1.45;
  color: var(--text-muted);
}
</style>
