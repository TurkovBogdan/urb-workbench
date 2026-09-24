<script setup lang="ts">
// Панель раздела групп: поиск и «показать сверх обычного» — та же анатомия, что у `TaskFilters`,
// урезанная до того, что у групп есть. Областей глубины у поиска нет: у группы нет ничего, кроме
// названия и описания, и искать глубже негде.
//
// Значения живут в сторе раздела, а не здесь: поиск переживает уход со страницы и возврат на неё.
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { IconTrash } from '@tabler/icons-vue'

import SearchField from '@/components/SearchField.vue'

import { useGroupsStore } from '../stores/groups.store'

const { t } = useI18n()
const store = useGroupsStore()

const EXTRA_DELETED = 'deleted'

/** Нажатая кнопка = показано. Корзина стоит нового запроса: удалённых в обычном ответе нет. */
const extras = computed({
  get: () => (store.includeDeleted ? [EXTRA_DELETED] : []),
  set: (keys: string[]) => {
    const deleted = keys.includes(EXTRA_DELETED)
    if (deleted !== store.includeDeleted) void store.showDeleted(deleted)
  },
})
</script>

<template>
  <div class="group-filters">
    <SearchField
      v-model="store.query"
      :placeholder="t('tasks.group.filter.query')"
      density="compact"
      class="group-filters__search"
    />

    <!-- Группа из одной кнопки, а не тумблер: так же выглядит «Удалённые» в панели задач, и один
         переключатель не должен выглядеть по-разному на соседних страницах. -->
    <VBtnToggle
      v-model="extras"
      multiple
      variant="outlined"
      divided
      density="compact"
      color="primary"
      class="group-filters__extras"
    >
      <VBtn :value="EXTRA_DELETED" size="small">
        <template #prepend><IconTrash :size="16" :stroke-width="1.7" /></template>
        {{ t('tasks.group.filter.deleted') }}
      </VBtn>
    </VBtnToggle>
  </div>
</template>

<style scoped>
/* Размеры и поведение ряда — те же, что у `TaskFilters`: поиск не уже 300px, переключатели прижаты
   к правому краю и в узком окне переносятся целиком. */
.group-filters {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
}

.group-filters__search {
  flex: 0 1 364px;
  min-width: 300px;
}

.group-filters__search :deep(.v-field__input) { font-size: 13px; }
.group-filters__search :deep(.v-field__prepend-inner) { color: var(--text-faint); }

.group-filters__extras {
  flex: none;
  margin-inline-start: auto;
}

.group-filters__extras :deep(.v-btn) { font-size: 12px; }
</style>
