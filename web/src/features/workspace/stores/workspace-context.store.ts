import { computed, ref } from 'vue'
import { defineStore } from 'pinia'

import { persisted, strCodec } from '@/shared/utils/persisted'

import { listWorkspaces, type WorkspaceRow } from '../api'

/**
 * Текущее пространство: в каком из них человек сейчас работает.
 *
 * Отдельно от `workspaces.store`, потому что роли разные: тот держит СТРАНИЦУ пространств
 * (тумблер корзины, счётчики, восстановление) и живёт её жизнью, а здесь — контекст всего
 * приложения: он переживает страницы, нужен сайдбару на любом маршруте и переживает
 * перезагрузку вкладки.
 *
 * Набор попадает сюда с двух сторон, как в справочнике полок: `adopt` — когда список уже пришёл
 * на страницу (второй раз спрашивать бэк незачем), `ensure` — когда пространства понадобились
 * месту, которое их не грузило (сайдбар при старте). `loaded` отличает «ещё не спрашивали» от
 * «спросили, и пространств нет»: без этого пустой набор перезапрашивался бы при каждом показе.
 *
 * Удалённые сюда не попадают ни одним из путей: в корзине не работают, и выбрать выброшенное
 * пространство значило бы открыть контекст, которого для остального приложения уже нет.
 */

// Ключ в стиле соседей (`ui.sort.researches.by`): `ui.` — состояние интерфейса, живущее только
// в браузере, дальше модуль и сама величина.
const STORAGE_KEY = 'ui.tasks.workspace'

/** Ничего не выбрано: пространств нет вовсе либо список ещё не приехал. */
const NOTHING = ''

export const useWorkspaceContextStore = defineStore('tasks-workspace-context', () => {
  const items = ref<WorkspaceRow[]>([])
  const loading = ref(false)
  const loaded = ref(false)

  // Умолчание — пусто, поэтому у того, кто ничего не выбирал, ключа в хранилище нет: первое
  // пространство он получит из списка, а не из вчерашней записи (см. `persisted`).
  const current = persisted(STORAGE_KEY, NOTHING, strCodec)

  // Один запрос на всех: сайдбар и страница, стартующие вместе, ждут общий, а не шлют по своему.
  let inflight: Promise<void> | null = null

  const isEmpty = computed(() => loaded.value && !items.value.length)

  const currentWorkspace = computed<WorkspaceRow | null>(
    () => items.value.find((workspace) => workspace.code === current.value) ?? null,
  )

  /**
   * Свести выбор с набором: сохранённого кода может уже не быть (пространство удалили в другой
   * вкладке), а выбора может не быть вовсе (первый заход). И то и другое — не отказ: молча
   * встаём на первое доступное, а на пустом наборе снимаем выбор.
   */
  function reconcile(): void {
    if (items.value.some((workspace) => workspace.code === current.value)) return
    current.value = items.value[0]?.code ?? NOTHING
  }

  /** Набор пришёл со стороны (страница пространств уже его загрузила). */
  function adopt(rows: WorkspaceRow[]): void {
    items.value = rows.filter((row) => row.deleted_at === null)
    loaded.value = true
    reconcile()
  }

  async function ensure(): Promise<void> {
    if (loaded.value) return
    if (inflight) return inflight
    loading.value = true
    inflight = (async () => {
      try {
        // `report: false` — молчаливый отказ: список едет фоном под элементом панели, и тост о
        // нём человек не связал бы с тем, что делает. Заглушка «пространств нет» честнее тоста.
        adopt(await listWorkspaces({}, { report: false }))
      } catch {
        items.value = []
      } finally {
        loading.value = false
        inflight = null
      }
    })()
    return inflight
  }

  /**
   * Смена пространства — только смена контекста: никакой навигации здесь нет и быть не должно,
   * человек остаётся ровно там, где стоял.
   */
  function select(code: string): void {
    if (code === current.value) return
    current.value = code
  }

  return { items, loading, loaded, current, currentWorkspace, isEmpty, adopt, ensure, select }
})
