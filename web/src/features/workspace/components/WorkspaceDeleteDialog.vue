<script setup lang="ts">
// Мягкое удаление пространства: вопрос, который честно называет, сколько внутри, и говорит, что
// действие обратимо.
//
// Числа берутся из строки списка, а не запрашиваются при открытии: они уже приехали со
// списком, и второй запрос показал бы то же самое, но на кадр позже. Без них окно просило бы
// подтвердить неизвестное — «содержимое останется» не ответ на вопрос «а сколько его там».
//
// Перечисление собирается из счётчиков (`content.ts`), а не пишется в словаре: что именно лежит
// внутри, знают модули поверх, и следующий из них не должен править эту фразу.
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'

import AppDialog from '@/components/AppDialog.vue'
import { errorText } from '@/api/errorText'

import { deleteWorkspace, type WorkspaceListRow } from '../api'
import { contentSummary, hasContent } from '../content'

const open = defineModel<boolean>({ required: true })

const props = defineProps<{ workspace: WorkspaceListRow | null }>()
const emit = defineEmits<{ deleted: [] }>()

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
  if (!props.workspace) return
  busy.value = true
  error.value = null
  try {
    // Отказ показываем в окне, а не тостом: человек смотрит сюда и здесь же решает, что делать.
    await deleteWorkspace(props.workspace.code, { report: false })
    open.value = false
    emit('deleted')
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

      <!-- Обратимость сказана отдельной строкой и приглушённо: это не предупреждение, а то, что
           снимает страх перед кнопкой. Смешай её с первой строкой — и она потеряется. -->
      <p class="workspace-delete__note">{{ t('workspace.delete.reversible') }}</p>

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

.workspace-delete__note {
  margin: 0;
  font-size: 12px;
  line-height: 1.45;
  color: var(--text-muted);
}
</style>
