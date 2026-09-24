import { getCurrentInstance, onActivated, onBeforeUnmount, onDeactivated, onMounted } from 'vue'

import { useChangesStore, type Change } from '@/stores/changes'

// Подписка экрана на ленту изменений — вместе с жизнью этого экрана.
//
// Всё, что в такой подписке ломается, собрано здесь, а не в каждом экране. У подписки три
// состояния, и в каждый момент она ровно в одном:
//
// - ВИДЕН (смонтирован или вернулся из `KeepAlive`) — свои изменения копятся `BATCH_MS` с
//   последнего и уходят в `onChange` одной пачкой: агент делает пять вызовов подряд — экран
//   перечитывается один раз; переподключение ленты — `onResync`;
// - СКРЫТ (страница жива в `KeepAlive`, но не на экране) — свои изменения не обрабатываются, а
//   только замечаются; при возвращении — одна перечитка (`onResync`), и только если было что.
//   Страница, которая при возвращении перечитывается и сама (`reloadsOnReturn`), вторую не
//   получает: два одинаковых запроса подряд ничего не добавляют;
// - СНЯТ (размонтирован) — ни одного обработчика в сторе не остаётся.
//
// Смена состояния сначала снимает все обработчики прежнего, потом ставит новые: утечь
// «наблюдатель скрытого» в видимое состояние или обработчик — за пределы жизни экрана не может.
// Эхо своих правок сюда не доходит вовсе — его отсевает стор (`stores/changes.ts`).

/** Сколько ждём тишины после изменения, прежде чем отдать пачку экрану. */
const BATCH_MS = 250

export interface ChangeSubscription {
  /** Какие сущности слушать (`tasks.task`, `tasks.stage`, …). */
  entities: string[]
  /** Это изменение про меня? Зовётся на каждое изменение слушаемых сущностей. */
  match: (change: Change) => boolean
  /** Пачка своих изменений — после `BATCH_MS` тишины. */
  onChange: (changes: Change[]) => void
  /** Перечитать всё: переподключение ленты или возвращение экрана после пропущенного. */
  onResync: () => void
  /** Экран перечитывается сам в `onActivated` — пропущенное за время скрытия он покроет им. */
  reloadsOnReturn?: boolean
}

type State = 'visible' | 'hidden' | 'disposed'

export function useChangeSubscription(spec: ChangeSubscription): void {
  if (!getCurrentInstance()) {
    throw new Error('useChangeSubscription must be called from a component setup')
  }
  const changes = useChangesStore()

  let state: State | null = null
  let missed = false
  let offs: Array<() => void> = []
  let batch: Change[] = []
  let timer: ReturnType<typeof setTimeout> | undefined

  function unsubscribe(): void {
    for (const off of offs) off()
    offs = []
  }

  function flush(): void {
    timer = undefined
    const pending = batch
    batch = []
    if (pending.length) spec.onChange(pending)
  }

  function dropBatch(): boolean {
    const had = batch.length > 0
    clearTimeout(timer)
    timer = undefined
    batch = []
    return had
  }

  function show(): void {
    if (state === 'visible' || state === 'disposed') return
    unsubscribe()
    state = 'visible'
    offs = [
      ...spec.entities.map((entity) =>
        changes.on(entity, (change) => {
          if (!spec.match(change)) return
          batch.push(change)
          clearTimeout(timer)
          timer = setTimeout(flush, BATCH_MS)
        }),
      ),
      changes.onResync(() => spec.onResync()),
    ]
    if (missed) {
      missed = false
      if (!spec.reloadsOnReturn) spec.onResync()
    }
  }

  function hide(): void {
    if (state !== 'visible') return
    unsubscribe()
    state = 'hidden'
    // Недоотданная пачка не теряется: экран перечитается, когда вернётся.
    if (dropBatch()) missed = true
    offs = [
      ...spec.entities.map((entity) =>
        changes.on(entity, (change) => {
          if (spec.match(change)) missed = true
        }),
      ),
      changes.onResync(() => { missed = true }),
    ]
  }

  function dispose(): void {
    unsubscribe()
    dropBatch()
    state = 'disposed'
  }

  // У страницы в `KeepAlive` при первом показе срабатывают оба хука; `show` повтор не заметит.
  onMounted(show)
  onActivated(show)
  onDeactivated(hide)
  onBeforeUnmount(dispose)
}
