import { computed, ref, watch } from 'vue'
import { defineStore } from 'pinia'

import { listGroups, restoreGroup, type GroupListRow } from '../api'
import { useWorkspaceContextStore } from '@/features/workspace/stores/workspace-context.store'

// Группы ТЕКУЩЕГО пространства: раздел привязан к контексту, выбранному в боковой панели, и своего
// переключателя пространств у него нет — второй выбор того же самого разошёлся бы с первым.
//
// Смена пространства перечитывает список сама: страница про это не знает, иначе о смене пришлось
// бы помнить каждому, кто группы показывает.
//
// Показ удалённых — перезапрос, а не маска поверх загруженного: без флага удалённые с бэка не
// приезжают вовсе, и фильтровать на клиенте было бы нечего.
export const useGroupsStore = defineStore('tasks-groups', () => {
  const context = useWorkspaceContextStore()

  const items = ref<GroupListRow[]>([])
  const loading = ref(true)
  const error = ref<unknown>(null)
  const includeDeleted = ref(false)
  const query = ref('')

  const workspace = computed(() => context.current)
  const noWorkspace = computed(() => context.loaded && !context.currentWorkspace)
  const isEmpty = computed(() => items.value.length === 0)

  // Поиск — на клиенте: групп в пространстве единицы, и все они уже загружены. Ищется по названию
  // и описанию, без регистра; `toLocaleLowerCase` сворачивает и кириллицу.
  const visible = computed(() => {
    const needle = query.value.trim().toLocaleLowerCase()
    if (!needle) return items.value
    return items.value.filter((group) =>
      `${group.title}\n${group.description}`.toLocaleLowerCase().includes(needle),
    )
  })
  /** Группы есть, но поиск не оставил ни одной. */
  const isFilteredOut = computed(() => !isEmpty.value && visible.value.length === 0)

  async function load() {
    // Набор пространств может быть ещё не загружен: раздел открывают и прямой ссылкой, не только
    // переходом из панели.
    await context.ensure()

    const code = workspace.value
    if (!code) {
      items.value = []
      loading.value = false
      return
    }

    error.value = null
    try {
      // `report: false` — отказ чтения раздела показывает сама страница (SectionError);
      // тост поверх него был бы вторым сообщением об одном и том же.
      items.value = await listGroups(
        { workspace: code, include_deleted: includeDeleted.value },
        { report: false },
      )
    } catch (e) {
      error.value = e
      items.value = []
    } finally {
      loading.value = false
    }
  }

  watch(workspace, () => { void load() })

  function showDeleted(enabled: boolean) {
    includeDeleted.value = enabled
    return load()
  }

  // Восстановление — единственное действие без своего окна: оно обратимо (кнопка «Удалить» стоит
  // на той же карточке), и подтверждение было бы вопросом ни о чём. Отказ показывает тост
  // клиента; список всё равно перечитывается — расхождение с базой и есть обычная причина отказа.
  async function restore(code: string) {
    try {
      await restoreGroup(code)
    } catch {
      // Об отказе уже сказал тост.
    }
    await load()
  }

  return {
    items,
    visible,
    query,
    loading,
    error,
    includeDeleted,
    isEmpty,
    isFilteredOut,
    noWorkspace,
    load,
    showDeleted,
    restore,
  }
})
