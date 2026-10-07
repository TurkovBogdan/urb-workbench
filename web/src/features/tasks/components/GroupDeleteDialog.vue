<script setup lang="ts">
// Deleting a group, and saying what becomes of its tasks in the same breath.
//
// A deleted group is drawn nowhere, so tasks left pointing at it vanished from the list while
// still existing. The backend now refuses to soft-delete a group with live tasks unless it is told
// their fate, and this dialog is where the person tells it: take the group off them, move them to
// another group, or send them to the trash. Each option is a card with what it does, because the
// difference between them is the consequence, and a button row has room only for the name.
//
// Nothing is pre-picked: all three are legitimate, and a default would be a choice made for the
// person on the one screen where the choice is the point. An empty group needs no choice at all.
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'

import AppDialog from '@/components/AppDialog.vue'
import ChoiceCards, { type ChoiceCard } from '@/components/ChoiceCards.vue'
import IconSwatch from '@/components/IconSwatch.vue'
import VSelectSearch from '@/components/VSelectSearch.vue'

import type { GroupListRow, GroupTaskDisposal } from '../api'

const open = defineModel<boolean>({ required: true })

const props = defineProps<{
  group: GroupListRow | null
  /** Every live group of the workspace — the move targets are the others. */
  groups: GroupListRow[]
  loading?: boolean
}>()

const emit = defineEmits<{ confirm: [fate: { tasks?: GroupTaskDisposal; target?: string }] }>()

const { t } = useI18n()

const disposal = ref<GroupTaskDisposal | null>(null)
const target = ref<string | null>(null)

// A fresh choice every time the dialog opens: carrying the last one over would delete the next
// group's tasks on a reflex click.
watch(open, (isOpen) => {
  if (!isOpen) return
  disposal.value = null
  target.value = null
})

const count = computed(() => props.group?.task_count ?? 0)

const targets = computed(() =>
  props.groups
    .filter((group) => group.code !== props.group?.code && !group.deleted_at)
    .map((group) => ({ value: group.code, title: group.title, icon: group.icon, color: group.color })),
)

// The texts agree with the count — "the task moves" for one, "the tasks move" for several — so
// every string with forms gets the number.
const options = computed<ChoiceCard<GroupTaskDisposal>[]>(() => [
  {
    value: 'ungroup',
    title: t('tasks.group.delete.ungroup.title', count.value),
    description: t('tasks.group.delete.ungroup.description', count.value),
  },
  {
    value: 'move',
    title: t('tasks.group.delete.move.title'),
    description: targets.value.length
      ? t('tasks.group.delete.move.description', count.value)
      : t('tasks.group.delete.move.no_targets'),
    disabled: !targets.value.length,
  },
  {
    value: 'delete',
    title: t('tasks.group.delete.delete.title', count.value),
    description: t('tasks.group.delete.delete.description', count.value),
  },
])

const ready = computed(() => {
  if (count.value === 0) return true
  if (disposal.value === 'move') return Boolean(target.value)
  return disposal.value !== null
})

function confirm() {
  if (!ready.value) return
  if (count.value === 0) emit('confirm', {})
  else if (disposal.value === 'move') emit('confirm', { tasks: 'move', target: target.value ?? undefined })
  else emit('confirm', { tasks: disposal.value ?? undefined })
}
</script>

<template>
  <AppDialog
    v-model="open"
    :title="t('tasks.group.delete.title')"
    :description="props.group?.title"
    size="base"
    :persistent="props.loading"
    :close-disabled="props.loading"
  >
    <!-- Laid out like the workspace's delete dialog: the question on the main line, reversibility
         on its own muted line — it is not a warning but what takes the fear out of the button,
         and merged into the question it gets lost. -->
    <div class="group-delete">
      <p class="group-delete__text">
        {{ count === 0 ? t('tasks.group.delete.empty') : t('tasks.group.delete.has_tasks', count) }}
      </p>

      <ChoiceCards v-if="count > 0" v-model="disposal" :items="options" :label="t('tasks.group.delete.choice')">
        <!-- The same group picker as on the task page — groups are recognised by their icon in
             their color — at the default density: here it is the one field of the dialog, not a
             row in a dense side panel. `:chips="false"` for the same reason as there: with chips
             Vuetify renders `#chip` and ignores `#selection`, losing the icon. -->
        <template #details="{ item }">
          <VSelectSearch
            v-if="item.value === 'move'"
            v-model="target"
            :items="targets"
            :label="t('tasks.group.delete.move.target')"
            :search-placeholder="t('tasks.task.detail.group_search')"
            :no-data-text="t('tasks.task.detail.group_empty')"
            :chips="false"
            variant="outlined"
            hide-details
          >
            <template #item="{ props: itemProps, item: group }">
              <VListItem v-bind="itemProps">
                <template #prepend>
                  <IconSwatch :icon="group.icon" :color="group.color" :width="20" />
                </template>
              </VListItem>
            </template>

            <template #selection="{ item: group }">
              <span class="group-delete__target">
                <IconSwatch :icon="group.icon" :color="group.color" :width="20" />
                {{ group.title }}
              </span>
            </template>
          </VSelectSearch>
        </template>
      </ChoiceCards>

      <p class="group-delete__note">
        {{ count === 0 ? t('tasks.group.delete.reversible') : t('tasks.group.delete.reversible_without_tasks') }}
      </p>
    </div>

    <template #actions>
      <VBtn variant="text" :disabled="props.loading" @click="open = false">
        {{ t('common.action.cancel') }}
      </VBtn>
      <VBtn color="error" variant="flat" :loading="props.loading" :disabled="!ready" @click="confirm">
        {{ t('tasks.group.delete.confirm') }}
      </VBtn>
    </template>
  </AppDialog>
</template>

<style scoped>
/* The type scale of `WorkspaceDeleteDialog`: the question at 14px in the main text color, the
   reversibility note at 12px muted, 12px apart. */
.group-delete {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.group-delete__text {
  margin: 0;
  font-size: 14px;
  line-height: 1.5;
  color: var(--text);
}

.group-delete__note {
  margin: 0;
  font-size: 12px;
  line-height: 1.45;
  color: var(--text-muted);
}

/* As `.task-page__group-value`: the picked group reads like the list item it was picked from. */
.group-delete__target {
  display: inline-flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
}
</style>
