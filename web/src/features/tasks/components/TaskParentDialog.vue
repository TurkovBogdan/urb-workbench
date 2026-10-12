<script setup lang="ts">
// Moving a subtask under another parent.
//
// Only a live, unfinished top-level task can take it: the tree is one level deep, so a subtask
// cannot be a parent, and finished work is history — the backend refuses an open subtask under a
// closed parent anyway, and offering what will be refused is a trap. The candidates are read when
// the dialog opens, not kept from the list: the list may be on another page or filtered.
//
// Each candidate carries its group's icon: the subtask takes the new parent's group, and the
// person should see that before choosing, not discover it afterwards in the side panel.
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'

import AppDialog from '@/components/AppDialog.vue'
import IconSwatch from '@/components/IconSwatch.vue'
import VSelectSearch from '@/components/VSelectSearch.vue'

import { listTasks, type GroupRow, type TaskDetail, type TaskListRow } from '../api'
import { TASK_STATUSES_TERMINAL, type TaskStatus } from '../labels'

const open = defineModel<boolean>({ required: true })

const props = defineProps<{
  task: TaskDetail | null
  /** The workspace's groups — the candidates are drawn with their group's icon. */
  groups: GroupRow[]
  loading?: boolean
}>()

const emit = defineEmits<{ confirm: [parentCode: string] }>()

const { t } = useI18n()

const candidates = ref<TaskListRow[]>([])
const fetching = ref(false)
const target = ref<string | null>(null)

// A fresh choice every time: carrying the last pick over would move the next subtask on a reflex
// click.
watch(open, (isOpen) => {
  if (!isOpen) return
  target.value = null
  void loadCandidates()
})

async function loadCandidates() {
  const task = props.task
  if (!task) return
  fetching.value = true
  try {
    const rows = await listTasks({ workspace: task.workspace_code })
    candidates.value = rows.filter(
      (row) =>
        row.parent_code === null &&
        row.code !== task.code &&
        row.code !== task.parent_code &&
        !TASK_STATUSES_TERMINAL.includes(row.status as TaskStatus),
    )
  } catch {
    candidates.value = []
  } finally {
    fetching.value = false
  }
}

const items = computed(() => {
  const byCode = new Map(props.groups.map((group) => [group.code, group]))
  return candidates.value.map((row) => {
    const group = row.group_code ? byCode.get(row.group_code) : undefined
    return { value: row.code, title: row.title, icon: group?.icon ?? '', color: group?.color ?? '' }
  })
})

function confirm() {
  if (target.value) emit('confirm', target.value)
}
</script>

<template>
  <AppDialog
    v-model="open"
    :title="t('tasks.task.parent.title')"
    :description="props.task?.title"
    size="base"
    :persistent="props.loading"
    :close-disabled="props.loading"
  >
    <div class="task-parent">
      <!-- `:chips="false"` for the same reason as the group field on the task page: with chips
           Vuetify renders `#chip` and ignores `#selection`, losing the icon. -->
      <VSelectSearch
        v-model="target"
        :items="items"
        :label="t('tasks.task.parent.target')"
        :search-placeholder="t('tasks.task.parent.search')"
        :no-data-text="t('tasks.task.parent.empty')"
        :loading="fetching"
        :chips="false"
        variant="outlined"
        hide-details
      >
        <template #item="{ props: itemProps, item }">
          <VListItem v-bind="itemProps">
            <template #prepend>
              <IconSwatch :icon="item.icon" :color="item.color" :width="20" />
            </template>
          </VListItem>
        </template>

        <template #selection="{ item }">
          <span class="task-parent__value">
            <IconSwatch :icon="item.icon ?? ''" :color="item.color ?? ''" :width="20" />
            {{ item.title }}
          </span>
        </template>
      </VSelectSearch>

      <p class="task-parent__note">{{ t('tasks.task.parent.note') }}</p>
    </div>

    <template #actions>
      <VBtn variant="text" :disabled="props.loading" @click="open = false">
        {{ t('common.action.cancel') }}
      </VBtn>
      <VBtn color="primary" variant="flat" :loading="props.loading" :disabled="!target" @click="confirm">
        {{ t('tasks.task.parent.confirm') }}
      </VBtn>
    </template>
  </AppDialog>
</template>

<style scoped>
.task-parent {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.task-parent__note {
  margin: 0;
  font-size: 12px;
  line-height: 1.45;
  color: var(--text-muted);
}

/* As `.task-page__group-value`: the picked task reads like the list item it was picked from. */
.task-parent__value {
  display: inline-flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
}
</style>
