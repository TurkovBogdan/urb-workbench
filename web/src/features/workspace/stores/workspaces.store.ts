import { computed, ref } from 'vue'
import { defineStore } from 'pinia'

import { listWorkspaces, restoreWorkspace, type WorkspaceListRow } from '../api'
import { useWorkspaceContextStore } from './workspace-context.store'

// Пространства модуля задач. Список короткий и без пагинации (пространство — верхний уровень
// раскладки, их заводят единицами), порядок задаёт бэк — по названию. Поэтому стор ничего не
// сортирует и не фильтрует: он помнит один переключатель и перезапрашивает.
//
// Показ удалённых — именно перезапрос, а не маска поверх загруженного: удалённые с бэка без
// флага не приезжают вовсе, и фильтровать на клиенте было бы нечего.
//
// Свежий список отдаётся контексту (`workspace-context.store`): страница — единственное место,
// где пространства заводят, переименовывают и удаляют, и второй копии набора, живущей своей
// жизнью, быть не должно — выбор в панели обновляется тем же запросом, что и карточки.
export const useWorkspacesStore = defineStore('tasks-workspaces', () => {
  const context = useWorkspaceContextStore()
  const items = ref<WorkspaceListRow[]>([])
  const loading = ref(true)
  const error = ref<unknown>(null)

  // Не переживает перезагрузку вкладки намеренно: «показать удалённые» — это разовый заход в
  // корзину, а не режим работы, и застрявший включённым тумблер каждый раз открывал бы список
  // вперемешку с тем, что человек уже выбросил.
  const includeDeleted = ref(false)

  const isEmpty = computed(() => items.value.length === 0)

  async function load() {
    error.value = null
    try {
      // `report: false` — отказ чтения раздела показывает сама страница (SectionError);
      // тост поверх него был бы вторым сообщением об одном и том же.
      items.value = await listWorkspaces(
        { include_deleted: includeDeleted.value },
        { report: false },
      )
      // Удалённые отсеет сам контекст: здесь они законная часть списка (тумблер корзины), а
      // там — пространство, в котором нельзя работать.
      context.adopt(items.value)
    } catch (e) {
      error.value = e
    } finally {
      loading.value = false
    }
  }

  function showDeleted(enabled: boolean) {
    includeDeleted.value = enabled
    return load()
  }

  // Восстановление — единственное действие без своего окна: оно обратимо (обратно кнопка
  // «Удалить» стоит на той же карточке), и спрашивать подтверждение было бы вопросом ни о чём.
  // Отказ здесь показывает тост клиента — своего места под сообщение у карточки нет, поэтому
  // исключение гасится: наружу его ловить некому, а необработанный промис ушёл бы в консоль.
  async function restore(code: string) {
    try {
      await restoreWorkspace(code)
    } catch {
      // Об отказе уже сказал тост. Список всё равно перечитываем: отказ обычно и означает,
      // что показанное разошлось с базой, и свежий список — это и есть ответ.
    }
    await load()
  }

  return { items, loading, error, includeDeleted, isEmpty, load, showDeleted, restore }
})
